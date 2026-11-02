#!/bin/sh
# 重新生成全部字体并装进游戏（配置见 fonts.json）。只生成某一套：sh build_fonts.sh rollout
# fonttool 在《美女肥皂剧》汉化仓库 https://github.com/Aden-c/SoapOperaDashCN 里（需 de1f223 之后的版本）；
# 用环境变量 FONTTOOL 指向它的 fonttool/fonttool.py
cd "$(dirname "$0")"
FONTTOOL="${FONTTOOL:-$HOME/OneDrive/Desktop/本地化归档/Soap_Opera_Dash_Win_Preinstalled_EN/hanhua/fonttool/fonttool.py}"
python -X utf8 "$FONTTOOL" build -p fonts.json "$@"
