

-- Main module for the remote-development-tools plugin
local M = {}

local uv = vim.uv or vim.loop

local utils = require('rdt.utils')

local function get_project_root_path()
	return vim.fs.root(0, {
		'.git',
		'compile_commands.json',
		'Package.swift',
		'buildServer.json'
	})
end


local function get_plugin_root_path()
	local current_dir = debug.getinfo(1, "S").source:sub(2)
	local parts = vim.fn.split(current_dir, '/')
	if parts[1] == current_dir then
		parts = vim.fn.split(current_dir, '\\')
	end
	return vim.fn.join(utils.slice(parts, 1, #parts - 3), '/')
end


---@param lsp_name string
local function get_lsp_wrapper_path(lsp_name)
	-- Ensure that word separators in lsp_name are '_' and not '-', so that the correct python script name is created
	if lsp_name:find('-') then
		lsp_name = lsp_name:gsub('-', '_')
	end
	-- local plugin_root = utils.joinstr(new_parts, '/')
	local plugin_root = get_plugin_root_path()
	local lsp_wrapper_name = lsp_name .. '_proxy.py'
	return vim.fs.joinpath(plugin_root, 'python', lsp_wrapper_name)
end


function M.get_host_name()
	local default_host_name = 'mac-clangd'
	local host_name = default_host_name
	local ssh_config_path = vim.fn.expand('$HOME/.ssh/config')
	local f = io.open(ssh_config_path, 'r')
	if not f then
		return host_name
	end
	local curr_line = f:read('*l')
	while curr_line do
		if string.len(curr_line) > 4 then
			if string.sub(curr_line, 1, 4) == 'Host' then
				f:close()
				host_name = utils.splitstr(curr_line, ' ')[2]
				return host_name
			end
		end
		curr_line = f:read('*l')
	end
	f:close()
	return host_name
end



local defaults = {
	name = 'myclangd_proxy',
	python = 'python',
	clangd_wrapper = get_lsp_wrapper_path('clangd'),
	clangd_exe = nil,
	sourcekit_lsp_wrapper = get_lsp_wrapper_path('sourcekit-lsp'),
	remote_host = M.get_host_name(),
	filetypes = {'c', 'cpp', 'objc', 'objcpp', 'cuda', 'proto'},
	query_driver = 'C:/msys64/mingw64/bin/*',
	root_markers = {'compile_commands.json', '.clangd', '.git', 'compile_flags.txt'},
	logging_enabled = false
}



-- Function to print the hello message
function M.say_hello()
	-- print(current_dir)
	print(defaults.clangd_wrapper)
end

---@param path string
local function load_json_from_path(path)
	local lines = vim.fn.readfile(utils.normalize_path(path))
	return vim.fn.json_decode(lines)
end

local function load_tracked_projects()
	local user_home = vim.fn.expand('~'):gsub('\\', '/')
	local tracked_projects_path = user_home .. '/.remote-development-tools/tracked-projects.json'
	return load_json_from_path(tracked_projects_path)
end

-- ---@param s string
-- local function logappend(s)
-- 	local f = io.open('C:/Users/sjber/Coding/RemoteDevelopmentTools/tmp.txt', 'a')
-- 	f:write(s .. '\n')
-- 	f:close()
-- end

-- Function to set up the plugin (Most package managers expect the plugin to have a setup function)
function M.setup(opts)
	local group = vim.api.nvim_create_augroup('Rdt', { clear = true })

	local user_home = utils.get_user_home()
	local rdt_home_path = vim.fs.joinpath(user_home, '.remote-development-tools')
	-- Ensure existence of ~/.remote-development-tools, and tracked_projects.json
	-- And yes I should fix the name of this folder for this project, but... meh
	if not uv.fs_stat(rdt_home_path) then
		vim.fn.mkdir(rdt_home_path, 'p')
	end

	-- Ensure existence of tracked projects file
	local tracked_projects_path = vim.fs.joinpath(rdt_home_path, 'tracked-projects.json')
	if not uv.fs_stat(tracked_projects_path) then
		local tracked_projects_file = io.open(tracked_projects_path, 'w')
		if tracked_projects_file then
			tracked_projects_file:write('{}')
			tracked_projects_file:flush()
			tracked_projects_file:close()
		end
	end

	-- Ensure existence of definition cache file
	local definition_cache_path = vim.fs.joinpath(rdt_home_path, 'definition-cache.json')
	if not uv.fs_stat(definition_cache_path) then
		local definition_cache_file = io.open(definition_cache_path, 'w')
		if definition_cache_file then
			definition_cache_file:write('{}')
			definition_cache_file:flush()
			definition_cache_file:close()
		end
	end

	-- Ensure existence of lsp-proxy-state.json.  I don't think this is even really used anymore, but the proxy will crash if it doesnt
	-- exist, and it's easier for now to just ensure it exists here rather than changing a bunch of python code
	local lsp_proxy_state_path = vim.fs.joinpath(rdt_home_path, 'lsp-proxy-state.json')
	if not uv.fs_stat(lsp_proxy_state_path) then
		local lsp_proxy_state_file = io.open(lsp_proxy_state_path, 'w')
		if lsp_proxy_state_file then
			lsp_proxy_state_file:write('{"active_projects":[]}')
			lsp_proxy_state_file:flush()
			lsp_proxy_state_file:close()
		end
	end




	opts = vim.tbl_deep_extend('force', defaults, opts or {})
	if not opts.clangd_wrapper then
		error('remote-development-tools: opts.wrapper is required')
	end


	-- Early error if no clangd_exe path is supplied
	if not opts.clangd_exe then
		vim.notify('Error in xcode-lsp-bridge: no clangd_exe path supplied.  Make sure you supply a clangd_exe argument pointing to the clangd executable on your system in the plugin config setup call', vim.log.levels.ERROR)
	end

	-- Check if logging is enabled, and if so, ensure that ~/tmp exists
	if opts.logging_enabled == true then
		local tmp_path = vim.fs.joinpath(vim.fn.expand('~'), 'tmp')
		if not uv.fs_stat(tmp_path) then
			vim.fn.mkdir(tmp_path)
		end
	end


	local opts_json_str = vim.json.encode(opts)
	local python_config_file_path = vim.fs.joinpath(rdt_home_path, 'lsp-proxy-config.json')
	local python_config_file = io.open(python_config_file_path, 'w')
	if python_config_file then
		python_config_file:write(opts_json_str)
		python_config_file:flush()
		python_config_file:close()
	-- else
		-- logappend('ERROR OPENING PYTHON_CONFIG_FILE: ' .. python_config_file_path .. ' FOR WRITING')
	end


	-- Create callback to Push sync to remote when a buffer is written
	vim.api.nvim_create_autocmd('BufWritePost', {
		group = group,
		callback = function(args)
			-- logappend('BufWritePost callback was called')
			-- local root_path = get_project_root_path()
			local root_path = get_project_root_path()
			-- Exit early and do nothing if root_path is nil.  This means that the file is not part of a tracked project
			if not root_path then
				return
			end
			-- logappend('root_path: ' .. root_path)
			local tracked_projects = load_tracked_projects()
			for _, proj_dct in pairs(tracked_projects) do
				local proj_root_unnormed = proj_dct['root_path']
				local proj_root = proj_root_unnormed
				if proj_root_unnormed then
					proj_root = string.gsub(proj_root_unnormed, '\\', '/')
				end
				if proj_root == root_path then
					-- print('Running sync for project at root_path: ' .. root_path)
					if proj_dct['sync_mode'] == 1 then
						local sync_project_path = root_path .. '/sync_project.py'
						local cmd = 'python ' .. sync_project_path .. ' --remote-host=' .. opts.remote_host .. ' ' .. root_path
						-- print('command: ' .. cmd)
						io.popen(cmd)
						break
						-- print('Saved buffer in a tracked project')
					else
						if proj_dct['sync_mode'] == 2 then
							local manage_project_path = root_path .. '/manage_project.py'
							local cmd = 'python ' .. manage_project_path .. 'autosync  --remote-host=' .. opts.remote_host .. ' ' .. root_path
							io.popen(cmd)
							break
						end


					end
					break
				end


			end
			-- logappend('END OF BUFWRITEPOST CALLBACK')


		end

	})

	local remote_host_arg = '--remotehost=' .. opts.remote_host
	local project_root = get_project_root_path()
	local project_root_arg = '--project-root=' .. (project_root or '')
	-- Merge user options with defaults
	--


	-- logappend('Detected project root arg: ' .. project_root_arg .. '\n')

	-- local host_name = M.get_host_name()
	local cmd = { opts.python, opts.clangd_wrapper, remote_host_arg, project_root_arg }
	if opts.query_driver then
		table.insert(cmd, '--query-driver=' .. opts.query_driver)
	end


	vim.lsp.config(opts.name, {
		cmd = cmd,
		filetypes = opts.filetypes,
		root_markers = opts.root_markers
	})

	vim.lsp.enable(opts.name)

	-- Also enable basic swift LSP features via sourcekit-lsp
	local sourcekit_lsp_cmd = { opts.python, opts.sourcekit_lsp_wrapper, remote_host_arg, project_root_arg}
	vim.lsp.config('sourcekit-lsp', {
		cmd = sourcekit_lsp_cmd,
		filetypes = {'swift'},
		root_markers = {'Package.swift', 'compile_commands.json', '.git'}
	})

	vim.lsp.enable('sourcekit-lsp')

end



return M
