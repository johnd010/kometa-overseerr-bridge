# kometa-overseerr-bridge
## About
Bridge containers for [Kometa](https://github.com/Kometa-Team/Kometa) to send requests for new collection content to Overseerr/Jellyseerr for approval instead of directly to Sonarr/Radarr.

This is a quick and dirty solution that I slapped together that's not that elegant, but it works.

## Configure Kometa Config
Your Kometa config's sonarr/radarr configs should point to the docker containers exposed ports:
```
sonarr:                            # Can be individually specified per library as well
  url: http://localhost:58989    # Enter Radarr server URL (Optional)
  token: kometa-shim-key                           # Enter Sonarr API Key (Optional)
  add_missing: true
radarr:                            # Can be individually specified per library as well
  url: http://localhost:57878    # Enter Radarr server URL (Optional)
  token: kometa-shim-key                           # Enter Radarr API Key (Optional)
  add_missing: true
```
## Quick Install
```
# clone the repo
git clone https://github.com/johnd010/kometa-overseerr-bridge.git ./

# put up the container
docker compose up -d
```

That's all.. Should now intercept requests from Kometa and pass them to your Overseerr/Jellyseerr instance.
