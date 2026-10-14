#!/usr/bin/env bash
set -e

sudo apt-get update
sudo apt-get install -y ffmpeg libopus0

pip install -r requirements.txt