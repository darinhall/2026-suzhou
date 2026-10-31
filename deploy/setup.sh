#!/bin/sh
# 在服务器上运行（代码已经在 ~/deskbot）：装依赖、systemd、nginx 站点、证书。可以重复跑。
#   sh ~/deskbot/deploy/setup.sh
set -eu
APP=/home/ubuntu/deskbot
DOMAIN=api-suzhou-hackathon.ppclaw.cn
PIP_INDEX=https://mirrors.cloud.tencent.com/pypi/simple   # 国内镜像

sudo apt-get install -y -q python3-venv certbot python3-certbot-nginx >/dev/null
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -i "$PIP_INDEX" -r "$APP/deploy/requirements.txt"

sudo cp "$APP/deploy/deskbot-hub.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable -q deskbot-hub
sudo systemctl restart deskbot-hub

chmod o+x /home/ubuntu   # nginx（www-data）要能读 sim/ 静态文件
if [ ! -f /etc/nginx/sites-available/$DOMAIN ] || ! grep -q ssl_certificate /etc/nginx/sites-available/$DOMAIN; then
  sudo cp "$APP/deploy/nginx-deskbot.conf" /etc/nginx/sites-available/$DOMAIN
  sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect
fi
sudo nginx -t && sudo systemctl reload nginx
systemctl --no-pager --lines=5 status deskbot-hub
