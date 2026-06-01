{ pkgs ? import <nixpkgs> {} }:

let
  local-helper = import ./dependency.nix;
in
rec {
  imports = [ ./module.nix ];
  my-package = pkgs.stdenv.mkDerivation {
    pname = "test-pkg";
    version = "1.0.0";
  };
}
