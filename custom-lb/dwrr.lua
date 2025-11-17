local http = require("socket.http")
local json = require("dkjson")


function get_cpu_usage()
  local url = "http://imgbox2:9090/api/v1/query?query="..
              "rate(container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name\"openslide_iiif-openslide\"})"
  local body, code = http.request(url)
  if code == 200 then
    local data = json.decode(body)
    return tonumber(data.data.result[1].value[1])
  end

  return nil

end
