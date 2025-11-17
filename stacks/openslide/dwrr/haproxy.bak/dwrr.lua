local json = require("cjson")
local http = require("socket.http")

local function get_weights()
    local body, code = http.request("http://openslide_agent:9200/weight")
    if code ~= 200 or not body then
        core.Warning("Agent API gagal, code=" .. tostring(code))
        return {}
    end
    local data = json.decode(body)
    if data and data.weights then
        return data.weights
    end
    return {}
end

core.register_task(function()
    while true do
        local weights = get_weights()

        for srv, weight in pairs(weights) do
            local cmd = "set server openslide_backends/" .. srv .. " weight " .. weight
            core.Info("Update: " .. cmd)
            core.cli_command(cmd)
        end

        core.msleep(1000) -- update tiap n detik
    end
end)

