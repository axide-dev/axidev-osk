Name:           axidev-osk
Version:        0.12.0
Release:        1%{?dist}
Summary:        On-screen keyboard overlay for Windows and Linux

License:        GPL-3.0-only AND MIT
URL:            https://github.com/axide-dev/axidev-osk
Source0:        %{url}/releases/download/v%{version}/axidev-osk-%{version}-source.zip

BuildArch:      x86_64

BuildRequires:  gcc
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  pkgconfig(libinput)
BuildRequires:  pkgconfig(libudev)
BuildRequires:  pkgconfig(xkbcommon)

Requires:       python3-pyside6
Requires:       qt6-qtwayland
Requires:       layer-shell-qt
Requires:       libinput
Requires:       systemd-libs
Requires:       libxkbcommon

%description
Axidev OSK is an on-screen keyboard overlay with real keyboard event emission,
modifier latching, and Wayland layer-shell support where available.

This package currently builds and ships the vendored axidev-io Python bindings
inside the same RPM. The long-term packaging direction is to split axidev-io
into its own Python package once it is published independently.

%prep
%autosetup -n axidev-osk

%build
pushd vendor/axidev-io-python
%pyproject_wheel
popd
%pyproject_wheel

%install
pushd vendor/axidev-io-python
%pyproject_install
popd
%pyproject_install

install -Dpm0644 packaging/linux/resources/70-axidev-io-uinput.rules \
    %{buildroot}%{_udevrulesdir}/70-axidev-io-uinput.rules

%post
getent group uinput >/dev/null || groupadd -r uinput
udevadm control --reload-rules >/dev/null 2>&1 || :
udevadm trigger /dev/uinput >/dev/null 2>&1 || :

%postun
if [ "$1" -eq 0 ]; then
    if [ "$(readlink /etc/udev/rules.d/70-axidev-io-uinput.rules 2>/dev/null || :)" = "/dev/null" ]; then
        rm -f /etc/udev/rules.d/70-axidev-io-uinput.rules
    fi
    rm -f %{_udevrulesdir}/70-axidev-io-uinput.rules
    udevadm control --reload-rules >/dev/null 2>&1 || :
    udevadm trigger /dev/uinput >/dev/null 2>&1 || :
fi

%files
%license LICENSE
%license vendor/axidev-io-python/LICENSE
%doc README.md
%{_bindir}/axidev-osk
%{python3_sitelib}/axidev_osk
%{python3_sitelib}/axidev_osk-*.dist-info
%{python3_sitearch}/axidev_io
%{python3_sitearch}/axidev_io-*.dist-info
%{_udevrulesdir}/70-axidev-io-uinput.rules

%changelog
* Sun May 03 2026 Axidev <contact@axide.dev> - 0.12.0-1
- Add initial RPM packaging recipe.
