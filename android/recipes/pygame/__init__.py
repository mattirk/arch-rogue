# pyright: reportMissingImports=false
"""python-for-android recipe for pygame-ce.

python-for-android's built-in recipe is named ``pygame`` but still targets the
classic pygame 2.1.0 source tree. Arch Rogue uses the pygame-ce distribution,
whose import package is also named ``pygame``. Keeping this local recipe named
``pygame`` makes p4a cross-compile every extension for each requested Android
ABI instead of treating ``pygame-ce`` as a recipe-less pip dependency and
copying a manylinux host wheel into the APK.
"""

from os.path import join

import sh

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory, info, shprint


class PygameCERecipe(CompiledComponentsPythonRecipe):
    version = "2.5.7"
    url = (
        "https://github.com/pygame-community/pygame-ce/"
        "archive/refs/tags/{version}.tar.gz"
    )

    name = "pygame"
    site_packages_name = "pygame"
    depends = [
        "sdl2",
        "sdl2_image",
        "sdl2_mixer",
        "sdl2_ttf",
        "setuptools",
        "jpeg",
        "png",
    ]
    hostpython_prerequisites = ["setuptools", "wheel", "Cython<=3.2.4"]
    patches = ["modern-setuptools-spawn.patch"]
    call_hostpython_via_targetpython = False
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            # pygame-ce retains setup.py and Setup.Android.SDL2.in specifically
            # for p4a. pyproject.toml must remain present because setup.py reads
            # the package version from it; install_python_package below bypasses
            # its normal Meson backend without moving the metadata file.
            with open(
                join("buildconfig", "Setup.Android.SDL2.in"),
                encoding="utf-8",
            ) as source:
                setup_template = source.read()

            png = self.get_recipe("png", self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe("jpeg", self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            mixer = self.get_recipe("sdl2_mixer", self.ctx)
            mixer_includes = "".join(
                f"-I{directory} " for directory in mixer.get_include_dirs(arch)
            )
            image = self.get_recipe("sdl2_image", self.ctx)
            image_includes = "".join(
                f"-I{directory} " for directory in image.get_include_dirs(arch)
            )

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I"
                    + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include")
                    + " -L"
                    + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
                    + " -L"
                    + png_lib_dir
                    + " -L"
                    + jpeg_lib_dir
                    + " -L"
                    + arch.ndk_lib_dir_versioned
                ),
                sdl_ttf_includes="-I"
                + join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                sdl_image_includes=image_includes,
                sdl_mixer_includes=mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes="",
            )
            # pygame-ce's Android template predates pygame.system. Arch Rogue
            # uses SDL_GetPrefPath through that module for private save storage.
            setup_file += "\nsystem src_c/system.c $(SDL) $(DEBUG)\n"
            with open("Setup", "w", encoding="utf-8") as target:
                target.write(setup_file)

    def install_python_package(self, arch, name=None, env=None, is_dir=True):
        """Install the already cross-compiled setup.py build without PEP 517.

        p4a's generic PythonRecipe switched to ``pip install .`` for Python
        3.14. For pygame-ce that selects the Meson pyproject backend and builds
        a host wheel. The older p4a install layout remains correct for this
        setup.py-based Android build; p4a byte-compiles the app bundle later.
        """

        del name, is_dir
        if env is None:
            env = self.get_recipe_env(arch)
        info(f"Installing {self.name} cross-compiled modules into site-packages")
        hostpython = sh.Command(self.hostpython_location)
        install_root = self.ctx.get_python_install_dir(arch.arch)
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(
                hostpython,
                "setup.py",
                "install",
                "-O2",
                f"--root={install_root}",
                "--install-lib=.",
                _env=env.copy(),
            )

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["ANDROID_ROOT"] = join(self.ctx.ndk.sysroot, "usr")
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env


recipe = PygameCERecipe()
