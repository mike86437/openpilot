#!/usr/bin/bash

function install_debug_softwares {
  sudo mount -o remount,rw /
  curl -s https://install.zerotier.com | sudo bash
  sudo systemctl stop zerotier-one
  sudo mkdir -p /data/zerotier/
  sudo mount -o remount,rw /
  sudo sed -i 's/\/usr\/sbin\/zerotier-one/\/usr\/sbin\/zerotier-one \/data\/zerotier\//g' /lib/systemd/system/zerotier-one.service
  sudo systemctl daemon-reload
  sudo systemctl start zerotier-one
  sudo zerotier-cli -D"/data/zerotier" join "$(cat /data/params/d/ZeroTier)"
}

install_debug_softwares