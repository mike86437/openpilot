#!/usr/bin/bash

function install_debug_softwares {
  sudo mount -o remount,rw /
  curl -s https://install.zerotier.com | sudo bash
  sudo systemctl stop zerotier-one
  
  # Check if the directory already exists
  if [ ! -d "/persist/zerotier" ]; then
    # If the directory doesn't exist, create it
    sudo mkdir -p /persist/zerotier/
  fi

  sudo mount -o remount,rw /
  
  # Check if the modification already exists in the file
  if ! sudo grep -q '/usr/sbin/zerotier-one -d"/persist/zerotier/"' /lib/systemd/system/zerotier-one.service; then
    # If the modification doesn't exist, apply it
    sudo sed -i 's|ExecStart=/usr/sbin/zerotier-one|ExecStart=/usr/sbin/zerotier-one -d"/persist/zerotier/"|' /lib/systemd/system/zerotier-one.service
  fi

  sudo systemctl daemon-reload
  sudo systemctl start zerotier-one

  # Proceed with joining ZeroTier network
  sudo zerotier-cli -D"/persist/zerotier" join "$(</data/params/d/ZeroTier)"
}

install_debug_softwares
