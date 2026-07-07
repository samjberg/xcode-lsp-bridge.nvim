
# xcode-lsp-bridge.nvim

This Neovim plugin acts as a bridge between a Windows PC, or Linux although this has not been tested, and a Mac, allowing you to get full LSP support with Apple frameworks inside of Neovim.

It supports both Objective-C/Objective-C++ via a `clangd` proxy, and Swift via a `sourcekit-lsp` proxy.

Once correctly installed, as long as the Mac you are using as the remote host is currently reachable, you will be able to write Swift/Objective-C/Objective-C++ code on your Windows PC in Neovim, including using Apple APIs/frameworks, as if doing so was natively supported in most ways. You will get syntax highlighting, code completion, go to definition, hover, etc.

A big feature of this plugin is a definition cache. Go to definition with `sourcekit-lsp`, the LSP used for Swift, can transfer HUUUUGE files when the definition leads to a generated Swift interface file. The first time you use go to definition on a symbol that leads to a generated Swift interface file, it will be transferred to your PC and added as a cache entry, both in memory and on disk. All subsequent uses of go to definition on that symbol will happen instantly because the definition location is retrieved from the cache. Context is used to differentiate between identical symbols that can mean different things in different contexts, so false positives are extremely rare. I have actually never seen it happen.

## What this is not

To be clear, this is NOT a full LSP on its own. It does NOT enable you to get LSP support with only a Windows machine. It absolutely requires having a Mac to use as a remote machine where the LSP can run.

## Requirements

1. A Mac, as already stated.

   a. The Mac must have the whole Xcode toolchain as well as `xcode-build-server`:
   https://github.com/SolaWing/xcode-build-server

   Shoutout to SolaWing, as their `xcode-build-server` made this project possible, although no code from it is directly included. It is simply an external requirement you must install on your own.

2. This plugin assumes that you have a "coding root" on both the local machine, where you are running Neovim, and on the remote Mac.

   Most core functionality relies on this fact. So you will have to supply a `local_coding_root` and a `remote_coding_root` in the config.

   Projects will get automatically mirrored from the local machine inside of `local_coding_root` to the remote Mac inside of `remote_coding_root`.

3. A minimum Neovim version of 0.11.

4. This project uses SSH to create the bridge to the LSP, either `clangd` or `sourcekit-lsp`, depending on the file type, running on the Mac.

   I have not tested using IP addresses directly, and I highly recommend having an SSH profile and using that as the `remote_host` parameter.

5. This isn't really specific to this plugin, but it is helpful to know that Xcode projects need a `buildServer.json`, and SwiftPM projects require a `Package.swift` in the project root in order for the LSP to correctly handle inter-file dependencies.

   a. For Xcode projects, you can generate `buildServer.json` with:

   ```sh
   xcode-build-server config -scheme {project_name} -project {project_name}.xcodeproj
   ```

   b. For SwiftPM projects, you just have to build the project once, and then LSP features should work.

## Installation

Honestly I find Neovim plugins kind of confusing, so this is designed to be used with Lazy.

What is shown here is how to install via Lazy, but you can also install by cloning this repo to a location of your choice, using the exact same code shown here, but adding a `dir =` argument before the `config =` argument, and pointing it to the root directory of this repo wherever you cloned it to.

The 5 required arguments to pass to `setup` are:

* `remote_host`: This represents the remote Mac. It should ideally be a pre-configured SSH profile, usually defined in `~/.ssh/config`.
* `remote_user_home`: The home directory on the remote Mac for the given user, probably your user account on that machine.
* `local_coding_root`: The root directory of where you store your coding projects. To work with this plugin, projects must be inside this folder. They do NOT need to be directly inside, just recursively inside of `local_coding_root`.
* `remote_coding_root`: The root directory of where you store coding projects on the remote Mac.
* `clangd_exe`: The path to the `clangd` executable on your system. I recommend using one inside of `nvim-data/mason/packages` as shown here.

There is also 1 additional semi-required argument. It may or may not be necessary depending on your setup.

If you have MSYS installed on your C drive, then it should not be necessary. Otherwise it is necessary:

* `query_driver`: Basically this is the path to a GCC toolchain.

Here is an example config that you would put inside of your Lazy block of your `init.lua`, along with other plugins.

Note that this is a specific example. Every single specific value you see must be replaced with your own, except for `'samjberg/xcode-lsp-bridge.nvim'` and `'rdt'`, which must be kept exactly as is. All other values must be changed to the correct values for your situation.

```lua
{
  'samjberg/xcode-lsp-bridge.nvim',
  config = function()
    require('rdt').setup({
      remote_host = 'my-mac',
      local_coding_root = 'C:/Users/you/Coding',
      remote_coding_root = '/Users/you/Coding',
      remote_user_home = '/Users/you',
      clangd_exe = 'C:/Users/you/AppData/Local/nvim-data/mason/packages/clangd/clangd_22.1.6/bin/clangd.exe',
      query_driver = 'C:/msys64/mingw64/bin/*'
    })
  end
}
```

`remote_host` should be the name you would use in a terminal command like:

```sh
ssh my-mac
```

For example, if your `~/.ssh/config` contains `Host mac-clangd`, use:

```lua
remote_host = 'mac-clangd'
```

not the Mac's display name.

## Project status / disclaimer

I thought that this functionality, the ability to write code for Apple/Xcode stuff like iOS apps on a Windows computer as long as you have a Mac to act as a server, might be genuinely helpful for others. It certainly has been for me.

However, this is originally part of a larger suite of tools I made for my own use. The larger codebase is very specific to my own setup, and also the Neovim plugin is contained inside of that larger project, so the larger project wouldn't work with plugin managers like Lazy if I just used the larger project as a GitHub repo.

So that is why I split off just the LSP stuff into this repo.

I have made a decent initial effort at removing hardcoded paths, and making it so that everything will work as long as you install it correctly. But I am NOT AT ALL completely sure that it actually will work for others yet. That is the disclaimer.

I DO NOT guarantee that this code will immediately work for you as is. However, I would like to get this repo into a state where it DOES just work out of the box for anyone installing it with Lazy, or manually by cloning this repo.

So I openly welcome anyone to submit issues, and I will try to fix them if they are genuine issues with the code itself.

Also, if anyone chooses to try to fix issues with this plugin on their own, and wants to submit a pull request to help me get this plugin working out of the box for anyone who wants to use it, I would appreciate that.

Any issues with it not working for you AT ALL should not be very difficult issues to fix. It's just that it would kind of be a pain to delete all of the things I would need to delete in order to test it all thoroughly, so I haven't done that yet.

## Note

If you care about this sort of thing, this project is not vibe coded at all. This is pure, artisinal, hand-crafted, home-baked human slop.
