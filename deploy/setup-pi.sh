#!/usr/bin/env bash
# PiHumMonitor 一键部署脚本（Raspberry Pi，选项 B：Pi 自托管 + Cloudflare Tunnel）
# 用法：把整个项目传到 Pi 后，在项目根目录执行：
#     bash deploy/setup-pi.sh
# 说明：需要 sudo 权限（安装系统包 / 写 systemd 单元时会提示密码）。
set -euo pipefail

# 解析项目根目录（脚本位于 deploy/ 下，上一级即根）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

c_ok="\033[32m"; c_info="\033[36m"; c_warn="\033[33m"; c_end="\033[0m"
step(){ echo -e "\n${c_info}[$1]${c_end} $2"; }

step "1/6" "安装系统依赖（python3 / venv / i2c-tools）"
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv i2c-tools wget

# 启用 I2C（真实硬件需要；模拟器模式不需要）
step "2/6" "启用 I2C（raspi-config nonint）"
sudo raspi-config nonint do_i2c 0 2>/dev/null || echo -e "${c_warn}  raspi-config 不可用，请手动在 sudo raspi-config 中启用 I2C${c_end}"

step "3/6" "创建 Python 虚拟环境并安装依赖"
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r server/requirements.txt -r sensor/requirements.txt

step "4/6" "安装 cloudflared（Cloudflare Tunnel，用于暴露公网）"
if command -v cloudflared >/dev/null 2>&1; then
    echo "  cloudflared 已安装，跳过"
else
    arch="$(dpkg --print-architecture)"
    case "$arch" in
        armhf) url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb" ;;
        arm64) url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb" ;;
        amd64) url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb" ;;
        *) echo -e "${c_warn}  未知架构 $arch，请手动安装 cloudflared${c_end}"; exit 1 ;;
    esac
    echo "  架构=$arch，下载 $url"
    wget -O /tmp/cloudflared.deb "$url"
    sudo dpkg -i /tmp/cloudflared.deb
    rm -f /tmp/cloudflared.deb
fi

step "5/6" "写入 systemd 服务（后端 + 采集，开机自启 + 崩溃重启）"
sudo tee /etc/systemd/system/pihum.service >/dev/null <<EOF
[Unit]
Description=PiHumMonitor backend (FastAPI)
After=network.target
[Service]
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/pihum-collect.service >/dev/null <<EOF
[Unit]
Description=PiHumMonitor collector (sensor -> server)
After=pihum.service
Requires=pihum.service
[Service]
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python sensor/collect.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pihum pihum-collect
sudo systemctl restart pihum pihum-collect

step "6/6" "验证本地服务"
sleep 2
if curl -fsS http://127.0.0.1:8000/api/health | grep -q '"ok":true'; then
    echo -e "${c_ok}  后端健康检查通过 ✓${c_end}"
else
    echo -e "${c_warn}  健康检查未通过，查日志：journalctl -u pihum -n 50 --no-pager${c_end}"
fi
systemctl is-active --quiet pihum        && echo -e "${c_ok}  pihum         active${c_end}"
systemctl is-active --quiet pihum-collect && echo -e "${c_ok}  pihum-collect active${c_end}"

cat <<NOTE

========================================================
 部署完成！
--------------------------------------------------------
 本地访问 : http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '<Pi-IP>'):8000
          或 http://localhost:8000
 查看日志 : journalctl -u pihum -f
            journalctl -u pihum-collect -f
 切真实传感器: 编辑 config.yaml -> sensor.mode: real
            然后 sudo systemctl restart pihum-collect
 开公网隧道: cloudflared tunnel --url http://localhost:8000
            （输出形如 https://xxx.trycloudflare.com，发给老板即可）
 稳定域名 : 注册 Cloudflare 账号 + 自有域名，配 named tunnel
========================================================
NOTE
