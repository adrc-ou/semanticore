#!/usr/bin/env bash
# Fresh-clone toolchain bootstrap (idempotent). Rebuilds what .gitignore skips.
set -e; cd "$(dirname "$0")/.."
if [ ! -x venv/bin/python ]; then
  python3 -m venv venv
  venv/bin/pip install --quiet --upgrade pip
  venv/bin/pip install --quiet -r requirements.txt
fi
mkdir -p tools && cd tools
if [ ! -d jdk-17.0.20.1+1-jre ]; then
  curl -sfL --retry 3 -o jre.tar.gz "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jre_x64_linux_hotspot_17.0.20.1_1.tar.gz"
  tar xzf jre.tar.gz && rm jre.tar.gz
fi
if [ ! -f vp/bin/cli-1.30.3.jar ]; then
  curl -sfL --retry 3 -o vp.zip "https://software.verapdf.org/releases/verapdf-installer.zip"
  unzip -q -o vp.zip -d vpinst
  JRE=../tools/jdk-17.0.20.1+1-jre/bin/java
  ( cd vpinst/verapdf-greenfield-*/ && ../../tools/jdk-17.0.20.1+1-jre/bin/java \
      -Djava.awt.headless=true -DINSTALL_PATH=$PWD/../../vp -jar verapdf-izpack-installer-*.jar -auto )
  rm -rf vp.zip vpinst
fi
cd ..
./venv/bin/python -c "import pikepdf, pymupdf, fontTools, PIL, numpy, pyphen; print('python deps ok')"
PATH=$PWD/tools/jdk-17.0.20.1+1-jre/bin:$PATH java -jar tools/vp/bin/cli-1.30.3.jar --version | head -1
echo "setup_env: OK"
