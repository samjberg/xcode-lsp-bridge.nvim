

local M = {}

local defaults = {
	name = 'myclangd_proxy',
	python = 'python',
	clangd_exe = 'C:/Users/sjber/AppData/Local/nvim-data/mason/packages/clangd/clangd_22.1.0/bin/clangd.exe',
	filetypes = {'c', 'cpp', 'objc', 'objcpp', 'cuda', 'proto'},
	query_driver = 'C:/msys64/mingw64/bin/*',
	root_markers = {'compile_commands.json', '.clangd', '.git', 'compile_flags.txt'}
}

function M.get_user_home()
	local uv = vim.uv or vim.loop
	local user_home = uv.os_homedir()
	return user_home
end

---@param lst table
---@param start number
---@param stop number
function M.slice(lst, start, stop)
	local new_lst = {}
	stop = math.min(stop, #lst)
	for i=start, stop, 1 do
		new_lst[#new_lst + 1] = lst[i]
	end
	return new_lst
end

-- Splits a string on the separator `sep` and returns the resulting list (table) of values
---@param str string
---@param sep string
function M.splitstr(str, sep)
  sep = sep or '\n'
  local lst = {}
  local function appendtolst(x) table.insert(lst, x) end
  local i = 1
  while (i <= string.len(str)) do
    local find_res = string.find(str, sep, i)
    if not find_res then break end
    local substr = string.sub(str, i, find_res-1)
	-- lst[#lst + 1] = substr
    -- table[#table + 1] = substr
    appendtolst(substr)
    i = find_res + 1
  end
  appendtolst(str:sub(i))
  return lst
end

-- Joins a list (table) into a single string, using sep as the separator
-- Using this function like joinstr(lst, sep) is equivalent to sep.join(lst) in python
---@param lst table
---@param sep string
function M.joinstr(lst, sep)
	local s = ''
	for i=1, #lst-1, 1 do
		s = s .. lst[i] .. sep
	end
	return s .. lst[#lst]
end
---
---@param lst table
---@param val any
function M.contains(lst, val)
	for _, v in pairs(lst) do
		if v == val then
			return true
		end
	end
	return false
end

---@param path string
---@param strip_drive boolean?
function M.normalize_path(path, strip_drive)
	strip_drive = strip_drive or false
	path = path:gsub('\\', '/')
	if strip_drive then
		if path:sub(2):starts(':/') then
			path = path:sub(3)
		end
	end
	return path
end


local function get_project_root_path()
	local cwd = vim.fn.getcwd()
	cwd = cwd:gsub('\\', '/')
	local root_markers = defaults.root_markers
	local path_parts = M.splitstr(cwd, '/')
	while #path_parts > 3 do
		local curr_path = M.joinstr(path_parts, '/')
		local dir_contents = vim.fn.readdir(curr_path)
		if #dir_contents > 0 then
			for _, path in pairs(dir_contents) do
				path = string.gsub(path, '\\', '/')
				local parts = M.splitstr(path, '/')
				local fname = parts[#parts]
				if M.contains(root_markers, fname) then
					return curr_path
				end
			end
		end
	end
	return nil
end


return M
