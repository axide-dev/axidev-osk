use std::env;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{self, Command};

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

fn main() {
    let root = payload_root();
    let python = required_path(PathBuf::from("/usr/bin/python3"), "system Python");
    let bootstrap = required_path(root.join("libexec/launch.py"), "Python bootstrap");
    required_path(root.join("lib/python"), "private Python tree");

    let mut command = Command::new(python);
    command
        .arg("-I")
        .arg(bootstrap)
        .args(env::args_os().skip(1))
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONUSERBASE")
        .env("PYTHONNOUSERSITE", "1")
        .env("AXIDEV_OSK_ROOT", &root);

    let error = command.exec();
    eprintln!("axidev-osk: cannot start system Python: {error}");
    process::exit(127);
}
