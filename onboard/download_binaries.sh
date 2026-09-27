#!/usr/bin/env bash
# Downloads the latest prometheus, blackbox_exporter, node_exporter, loki and alloy linux-amd64 releases into ~/nightshift-run/bin (needs curl, jq, unzip).
set -u
B=~/nightshift-run/bin
mkdir -p $B ~/nightshift-run/dl
cd ~/nightshift-run/dl
get() { # repo asset-regex
  url=$(curl -s "https://api.github.com/repos/$1/releases/latest" | jq -r --arg re "$2" '.assets[] | select(.name|test($re)) | .browser_download_url' | head -1)
  echo "$1 -> $url"
  [ -n "$url" ] && curl -sL -o "$(basename $url)" "$url"
}
get prometheus/prometheus 'linux-amd64\.tar\.gz$'
get prometheus/blackbox_exporter 'linux-amd64\.tar\.gz$'
get prometheus/node_exporter 'linux-amd64\.tar\.gz$'
get grafana/loki '^loki-linux-amd64\.zip$'
get grafana/alloy '^alloy-linux-amd64\.zip$'
ls -la
for f in *.tar.gz; do tar -xzf "$f"; done
for f in *.zip; do unzip -oq "$f"; done
cp prometheus-*/prometheus prometheus-*/promtool $B/
cp blackbox_exporter-*/blackbox_exporter $B/
cp node_exporter-*/node_exporter $B/
cp loki-linux-amd64 $B/loki
cp alloy-linux-amd64 $B/alloy
chmod +x $B/*
ls -la $B
$B/prometheus --version 2>&1 | head -1
$B/loki -version 2>&1 | head -1
$B/alloy --version 2>&1 | head -1
