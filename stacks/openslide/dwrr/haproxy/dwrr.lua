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

        -- cari backendd openslide_backends
        local be = core.backends["openslide_backends"]

        if be then
            for _, srv in pairs(be.servers) do
                local new_weight = weights[srv.name]
                if new_weight then
                    srv:set_weight(new_weight)
                    core.Info(os.date("%X") .. " | Update " .. srv.name .. " -> " .. new_weight)
                end
            end
        else
            core.Warning("Backend 'openslide_backends' tidak ditemukan")
        end


        core.msleep(5000) -- update tiap n detik
    end
end)

