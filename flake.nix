{
  description = "Axidev OSK on-screen keyboard";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3;
          axidev-io = python.pkgs.buildPythonPackage {
            pname = "axidev-io";
            version = "0.7.4";
            pyproject = true;
            src = ./vendor/axidev-io-python;

            nativeBuildInputs = with pkgs; [
              pkg-config
              python.pkgs.setuptools
              python.pkgs.wheel
            ];

            buildInputs = with pkgs; [
              libinput
              systemd
              libxkbcommon
            ];

            doCheck = false;
          };
        in
        rec {
          default = axidev-osk;

          axidev-osk = python.pkgs.buildPythonApplication {
            pname = "axidev-osk";
            version = "0.17.3";
            pyproject = true;
            src = self;

            nativeBuildInputs = with pkgs; [
              python.pkgs.setuptools
              python.pkgs.wheel
            ];

            propagatedBuildInputs = [
              axidev-io
              python.pkgs.pyside6
            ];

            buildInputs = with pkgs; [
              qt6.qtwayland
              kdePackages.layer-shell-qt
              libinput
              systemd
              libxkbcommon
            ];

            postInstall = ''
              install -Dm0644 packaging/linux/resources/70-axidev-io-uinput.rules \
                $out/lib/udev/rules.d/70-axidev-io-uinput.rules
            '';

            doCheck = false;

            meta = with pkgs.lib; {
              description = "On-screen keyboard overlay with real key emission";
              homepage = "https://github.com/axide-dev/axidev-osk";
              license = licenses.gpl3Only;
              mainProgram = "axidev-osk";
              platforms = platforms.linux;
            };
          };
        });

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python3
              python3Packages.pyside6
              qt6.qtwayland
              kdePackages.layer-shell-qt
              libinput
              systemd
              libxkbcommon
              pkg-config
              gcc
            ];
          };
        });

      nixosModules.default = import ./packaging/nix/module.nix self;
    };
}
