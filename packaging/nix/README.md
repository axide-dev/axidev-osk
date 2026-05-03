# Nix Packaging

The top-level `flake.nix` exposes:

- `packages.x86_64-linux.axidev-osk`
- `packages.x86_64-linux.default`
- `devShells.x86_64-linux.default`
- `nixosModules.default`

## Run

```bash
nix run github:axide-dev/axidev-osk
```

## Build

```bash
nix build .#axidev-osk
```

## NixOS Module

```nix
{
  inputs.axidev-osk.url = "github:axide-dev/axidev-osk";

  outputs = { self, nixpkgs, axidev-osk, ... }: {
    nixosConfigurations.example = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        axidev-osk.nixosModules.default
        {
          programs.axidev-osk = {
            enable = true;
            users = [ "iy" ];
          };
        }
      ];
    };
  };
}
```

The module installs the package, registers the bundled udev rule, and adds configured users to the `input` group.

## Dependency Policy

The Nix package uses Nix-provided PySide6, Qt6 Wayland, and layer-shell-qt rather than bundling them. Keeping those dependencies from the same package set avoids Qt ABI mismatches.
