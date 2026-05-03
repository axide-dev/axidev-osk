self:
{ config, lib, pkgs, ... }:
let
  cfg = config.programs.axidev-osk;
in
{
  options.programs.axidev-osk = {
    enable = lib.mkEnableOption "Axidev OSK";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.system}.axidev-osk;
      description = "Axidev OSK package to install.";
    };

    users = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "iy" ];
      description = "Users to add to the input group for /dev/uinput access.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    services.udev.packages = [ cfg.package ];
    users.groups.input.members = cfg.users;
  };
}
