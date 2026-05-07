-- Luau sample (Roblox): typed Lua superset.
-- tree-sitter-lua doesn't parse the type annotations, but extracts
-- function declarations and call edges fine.

local Server = {}
Server.__index = Server

type ServerConfig = {
	port: number,
	name: string?,
}

function Server.new(config: ServerConfig): Server
	local self = setmetatable({}, Server)
	self.port = config.port
	self.name = config.name or "default"
	return self
end

function Server:start(): ()
	print(string.format("listening on :%d", self.port))
end

function Server:stop(): ()
	print("stopped")
end

local function main()
	local s = Server.new({ port = 8080 })
	s:start()
end

main()

return Server
