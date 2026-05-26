{
  description = "flake for graphify using uv2nix";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs @ {
    flake-parts,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
    ...
  }:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "aarch64-darwin"];

      perSystem = {
        pkgs,
        lib,
        ...
      }: let
        pyproject = lib.importTOML ./pyproject.toml;
        projectMeta = pyproject.project;

        workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};

        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };

        python = pkgs.python312;

        baseSet =
          (pkgs.callPackage pyproject-nix.build.packages {
            inherit python;
          })
          .overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              overlay
            ]
          );

        pythonSet = baseSet.overrideScope (final: prev: {
          # numba manylinux wheel dlopens libtbb.so at runtime; expose it so
          # autoPatchelfHook (from pyproject-build-systems' wheel overlay) can
          # resolve it on the rpath.
          numba = prev.numba.overrideAttrs (old: {
            buildInputs = (old.buildInputs or []) ++ [pkgs.tbb];
          });

          # nuitka's sdist doesn't declare setuptools as a build dep.
          nuitka = prev.nuitka.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ final.resolveBuildSystem {setuptools = [];};
          });

          # jieba's sdist doesn't declare setuptools as a build dep.
          jieba = prev.jieba.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ final.resolveBuildSystem {setuptools = [];};
          });

          # tree-sitter-dm's sdist doesn't declare setuptools as a build dep.
          tree-sitter-dm = prev.tree-sitter-dm.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ final.resolveBuildSystem {setuptools = [];};
          });

          # Expose tests via passthru.tests so they can be wired into flake
          # checks (mirrors the uv2nix testing pattern).
          graphifyy = prev.graphifyy.overrideAttrs (old: {
            passthru =
              (old.passthru or {})
              // {
                tests = let
                  # Virtualenv containing graphify plus the dev dependency
                  # group (which carries pytest and friends).
                  testVenv = final.mkVirtualEnv "graphify-test-env" (workspace.deps.default
                    // {
                      graphifyy = ["dev"];
                    });
                in
                  (old.passthru.tests or {})
                  // {
                    pytest = pkgs.stdenv.mkDerivation {
                      name = "${final.graphifyy.name}-pytest";
                      inherit (final.graphifyy) src;
                      nativeBuildInputs = [testVenv pkgs.git];
                      dontConfigure = true;

                      buildPhase = ''
                        runHook preBuild
                        # The Nix build sandbox sets HOME=/homeless-shelter
                        # which is unwritable; several tests (e.g. the Gemini
                        # install ones) call helpers that resolve paths via
                        # Path.home() when not project-scoped. Point HOME at a
                        # writable temp dir so those tests pass under
                        # `nix flake check`.
                        export HOME=''${PWD}/home
                        pytest
                        runHook postBuild
                      '';

                      installPhase = ''
                        runHook preInstall
                        touch $out
                        runHook postInstall
                      '';
                    };
                  };
              };
          });
        });

        editablePythonSet = pythonSet.overrideScope editableOverlay;
        virtualenv = editablePythonSet.mkVirtualEnv "graphify-dev-env" workspace.deps.all;

        graphifyEnv = pythonSet.mkVirtualEnv "graphify-env" workspace.deps.default;

        # Wrap the virtualenv so the default package exposes the `graphify`
        # entry point directly while still carrying metadata from pyproject.toml.
        graphifyPackage = pkgs.stdenv.mkDerivation {
          pname = projectMeta.name;
          version = projectMeta.version;

          dontUnpack = true;
          dontBuild = true;
          dontConfigure = true;

          nativeBuildInputs = [pkgs.makeWrapper];

          installPhase = ''
            mkdir -p $out/bin
            makeWrapper ${graphifyEnv}/bin/graphify $out/bin/graphify
          '';

          passthru = {
            inherit graphifyEnv;
          };

          meta = {
            description = projectMeta.description;
            homepage = projectMeta.urls.Homepage;
            license = lib.licenses.mit;
            mainProgram = "graphify";
            platforms = lib.platforms.unix;
          };
        };
      in {
        devShells.default = pkgs.mkShell {
          packages = [
            virtualenv
            pkgs.uv
            pkgs.python3Packages.pytest
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = editablePythonSet.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
            UV_PROJECT_ENVIRONMENT = virtualenv.outPath;
            VIRTUAL_ENV = virtualenv.outPath;
          };

          shellHook = ''
            unset PYTHONPATH
            export REPO_ROOT=$(git rev-parse --show-toplevel)
          '';
        };

        packages.default = graphifyPackage;

        checks = {
          inherit (pythonSet.graphifyy.passthru.tests) pytest;
        };

        apps.default = {
          type = "app";
          program = "${graphifyPackage}/bin/graphify";
          meta = graphifyPackage.meta;
        };
      };
    };
}
