use std::env;
use std::ffi::{OsStr, OsString};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{self, Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex, TryLockError};
use std::thread;
use std::time::Duration;

const SERVICE_NAME: &str = "org.axidev.OSK.LockScreen";
const OBJECT_PATH: &str = "/org/axidev/OSK/LockScreen";
const INTERFACE_NAME: &str = "org.axidev.OSK.LockScreen";
const START_TIMEOUT: Duration = Duration::from_secs(15);
const COMMAND_TIMEOUT: Duration = Duration::from_secs(5);
const PING_INTERVAL: Duration = Duration::from_secs(5);
const PING_TIMEOUT: Duration = Duration::from_secs(2);

fn required_path(path: PathBuf, label: &str) -> PathBuf {
    if !path.exists() {
        eprintln!("axidev-osk: missing {label}: {}", path.display());
        process::exit(127);
    }
    path
}

fn payload_root() -> PathBuf {
    let executable = env::current_exe().unwrap_or_else(|error| {
        eprintln!("axidev-osk: cannot resolve launcher path: {error}");
        process::exit(127);
    });
    executable
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or_else(|| {
            eprintln!("axidev-osk: launcher is not inside the payload bin directory");
            process::exit(127);
        })
}

fn python_command(root: &Path) -> Command {
    let python = required_path(PathBuf::from("/usr/bin/python3"), "system Python");
    let bootstrap = required_path(root.join("libexec/launch.py"), "Python bootstrap");
    required_path(root.join("lib/python"), "private Python tree");

    let mut command = Command::new(python);
    command
        .arg("-I")
        .arg(bootstrap)
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONUSERBASE")
        .env("PYTHONNOUSERSITE", "1")
        .env("AXIDEV_OSK_ROOT", root);
    command
}

fn exec_python(root: &Path, arguments: impl IntoIterator<Item = OsString>) -> ! {
    let error = python_command(root).args(arguments).exec();
    eprintln!("axidev-osk: cannot start system Python: {error}");
    process::exit(127);
}

fn is_lock_supervisor(arguments: &[OsString]) -> bool {
    arguments.len() == 2
        && arguments[0] == OsStr::new("internal")
        && arguments[1] == OsStr::new("plasma-lock-supervisor")
}

struct Worker {
    child: Child,
    input: ChildStdin,
    responses: mpsc::Receiver<String>,
}

impl Worker {
    fn start(root: &Path) -> Result<Self, String> {
        let mut command = python_command(root);
        command
            .args(["internal", "plasma-lock-worker"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());

        // The worker must not survive its supervisor after KWin stops or replaces
        // the configured input-method process.
        unsafe {
            command.pre_exec(|| {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }

        let mut child = command
            .spawn()
            .map_err(|error| format!("cannot start Plasma lock worker: {error}"))?;
        let input = child
            .stdin
            .take()
            .ok_or_else(|| "Plasma lock worker has no command pipe".to_string())?;
        let output = child
            .stdout
            .take()
            .ok_or_else(|| "Plasma lock worker has no response pipe".to_string())?;
        let (sender, responses) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let Ok(line) = line else { break };
                if let Some(response) = line.strip_prefix("AXIDEV_OSK ") {
                    if sender.send(response.to_string()).is_err() {
                        break;
                    }
                }
            }
        });

        let mut worker = Self {
            child,
            input,
            responses,
        };
        worker.expect("READY", START_TIMEOUT)?;
        Ok(worker)
    }

    fn request(&mut self, command: &str, response: &str, timeout: Duration) -> Result<(), String> {
        if let Some(status) = self
            .child
            .try_wait()
            .map_err(|error| format!("cannot inspect Plasma lock worker: {error}"))?
        {
            return Err(format!("Plasma lock worker exited with {status}"));
        }
        if let Err(error) = writeln!(self.input, "{command}").and_then(|()| self.input.flush()) {
            let status = self
                .child
                .try_wait()
                .map_err(|inspect_error| {
                    format!(
                        "cannot send {command} to Plasma lock worker: {error}; cannot inspect worker: {inspect_error}"
                    )
                })?
                .map_or_else(|| "still running".to_string(), |status| status.to_string());
            return Err(format!(
                "cannot send {command} to Plasma lock worker: {error}; worker status: {status}"
            ));
        }
        self.expect(response, timeout)
    }

    fn expect(&mut self, expected: &str, timeout: Duration) -> Result<(), String> {
        match self.responses.recv_timeout(timeout) {
            Ok(response) if response == expected => Ok(()),
            Ok(response) => Err(format!(
                "Plasma lock worker returned {response}, expected {expected}"
            )),
            Err(mpsc::RecvTimeoutError::Timeout) => Err(format!(
                "Plasma lock worker did not return {expected} within {:.0}s",
                timeout.as_secs_f64()
            )),
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                Err("Plasma lock worker response pipe closed".to_string())
            }
        }
    }

    fn kill(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        self.kill();
    }
}

#[derive(Clone)]
struct LockScreenService {
    worker: Arc<Mutex<Worker>>,
}

impl LockScreenService {
    fn request(&self, command: &str, response: &str) {
        let result = self
            .worker
            .lock()
            .map_err(|_| "Plasma lock worker mutex is poisoned".to_string())
            .and_then(|mut worker| worker.request(command, response, COMMAND_TIMEOUT));
        if let Err(error) = result {
            recover_through_kwin(&error);
        }
    }
}

#[zbus::interface(name = "org.axidev.OSK.LockScreen")]
impl LockScreenService {
    #[zbus(name = "prepare")]
    fn prepare(&self) {
        self.request("PREPARE", "PREPARED");
    }

    #[zbus(name = "release")]
    fn release(&self) {
        self.request("RELEASE", "RELEASED");
    }
}

fn recover_through_kwin(error: &str) -> ! {
    eprintln!("axidev-osk: Plasma lock supervisor failure: {error}");
    // This must be a real signal-caused crash, not a non-zero normal exit.
    // KWin 6.7 only reports QProcess::CrashExit through its recovery branch;
    // that branch destroys the stale input-method connection, creates a new
    // privileged WAYLAND_SOCKET, and relaunches this configured command.
    process::abort();
}

fn run_lock_supervisor(root: &Path) -> Result<(), String> {
    if env::var_os("WAYLAND_SOCKET").is_none() {
        return Err("KWin did not provide WAYLAND_SOCKET".to_string());
    }
    let worker = Arc::new(Mutex::new(Worker::start(root)?));
    let interface = LockScreenService {
        worker: Arc::clone(&worker),
    };
    let _connection = zbus::blocking::connection::Builder::session()
        .map_err(|error| format!("cannot connect to the session bus: {error}"))?
        .name(SERVICE_NAME)
        .map_err(|error| format!("cannot own D-Bus service {SERVICE_NAME}: {error}"))?
        .serve_at(OBJECT_PATH, interface)
        .map_err(|error| format!("cannot export {INTERFACE_NAME}: {error}"))?
        .build()
        .map_err(|error| format!("cannot start D-Bus service {SERVICE_NAME}: {error}"))?;

    loop {
        thread::sleep(PING_INTERVAL);
        match worker.try_lock() {
            Ok(mut worker) => {
                if let Err(error) = worker.request("PING", "PONG", PING_TIMEOUT) {
                    recover_through_kwin(&error);
                }
            }
            Err(TryLockError::WouldBlock) => {}
            Err(TryLockError::Poisoned(_)) => {
                recover_through_kwin("Plasma lock worker mutex is poisoned")
            }
        }
    }
}

fn main() {
    let root = payload_root();
    let arguments: Vec<OsString> = env::args_os().skip(1).collect();
    if is_lock_supervisor(&arguments) {
        if let Err(error) = run_lock_supervisor(&root) {
            recover_through_kwin(&error);
        }
    }
    exec_python(&root, arguments)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fake_payload() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = env::temp_dir().join(format!("axidev-osk-launcher-test-{suffix}"));
        fs::create_dir_all(root.join("libexec")).unwrap();
        fs::create_dir_all(root.join("lib/python")).unwrap();
        fs::write(
            root.join("libexec/launch.py"),
            r#"import sys
print("AXIDEV_OSK READY", flush=True)
responses = {"PING": "PONG", "PREPARE": "PREPARED", "RELEASE": "RELEASED"}
for line in sys.stdin:
    print("AXIDEV_OSK " + responses.get(line.strip(), "ERROR"), flush=True)
"#,
        )
        .unwrap();
        root
    }

    #[test]
    fn only_private_plasma_lock_command_starts_supervisor() {
        assert!(is_lock_supervisor(&[
            OsString::from("internal"),
            OsString::from("plasma-lock-supervisor"),
        ]));
        assert!(!is_lock_supervisor(&[]));
        assert!(!is_lock_supervisor(&[OsString::from("--help")]));
        assert!(!is_lock_supervisor(&[
            OsString::from("internal"),
            OsString::from("plasma-lock-worker"),
        ]));
    }

    #[test]
    fn worker_protocol_waits_for_ready_and_command_acknowledgements() {
        let root = fake_payload();
        let mut worker = Worker::start(&root).unwrap();

        worker.request("PING", "PONG", PING_TIMEOUT).unwrap();
        worker
            .request("PREPARE", "PREPARED", COMMAND_TIMEOUT)
            .unwrap();
        worker
            .request("RELEASE", "RELEASED", COMMAND_TIMEOUT)
            .unwrap();

        drop(worker);
        fs::remove_dir_all(root).unwrap();
    }
}
