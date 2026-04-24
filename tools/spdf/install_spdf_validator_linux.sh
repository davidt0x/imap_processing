#!/usr/bin/env bash
set -euo pipefail
exec 3>&1
exec 1>&2

install_root="${1:-$(pwd)/.spdf-tools}"
cdf_root="${install_root}/cdf"
skt_root="${install_root}/skteditor"
cdf_index_url="https://spdf.gsfc.nasa.gov/pub/software/cdf/dist/latest_cdf/linux/"
skt_index_url="https://spdf.gsfc.nasa.gov/skteditor/index.html"
java_home="${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")}"

mkdir -p "${install_root}" "${cdf_root}" "${skt_root}"

cdf_tarball="$(curl -fsSL "${cdf_index_url}" | grep -o 'cdf[0-9_]\+-dist-all\.tar\.gz' | head -n 1)"
if [[ -z "${cdf_tarball}" ]]; then
  echo "Unable to find the latest Linux CDF all-in-one tarball at ${cdf_index_url}" >&2
  exit 1
fi

curl -fsSL "${cdf_index_url}${cdf_tarball}" -o "${install_root}/${cdf_tarball}"
tar -xzf "${install_root}/${cdf_tarball}" -C "${cdf_root}"
cdf_dist_dir="$(
  find "${cdf_root}" -maxdepth 1 -type d \( -name 'cdf*_dist*' -o -name 'cdf*-dist' \) | head -n 1
)"
if [[ -z "${cdf_dist_dir}" ]]; then
  echo "Unable to locate the extracted CDF distribution under ${cdf_root}." >&2
  exit 1
fi

make -C "${cdf_dist_dir}" OS=linux ENV=gnu CURSES=no JNI=yes JAVA_HOME="${java_home}" all

cdfjava_jar_path="$(find "${cdf_dist_dir}" -path '*/cdfjava/classes/cdfjava.jar' -print | head -n 1)"
cdf_native_lib_dir="$(find "${cdf_dist_dir}" -type d -path '*/src/lib' -print | head -n 1)"
cdf_jni_lib_dir="$(find "${cdf_dist_dir}" -type d -path '*/cdfjava/jni' -print | head -n 1)"
jni_native_library="$(find "${cdf_jni_lib_dir}" -maxdepth 1 -name 'libcdfNativeLibrary.so' -print | head -n 1)"

if [[ -z "${cdfjava_jar_path}" ]]; then
  echo "Unable to locate cdfjava.jar in ${cdf_dist_dir}." >&2
  exit 1
fi
if [[ -z "${cdf_native_lib_dir}" ]]; then
  echo "Unable to locate the native CDF library directory under ${cdf_dist_dir}." >&2
  exit 1
fi
if [[ -z "${cdf_jni_lib_dir}" || -z "${jni_native_library}" ]]; then
  echo "Unable to build the JNI CDF native library under ${cdf_dist_dir}/cdfjava/jni." >&2
  exit 1
fi

skt_deb_url="$(
  python - <<'PY'
import re
import urllib.request

html = urllib.request.urlopen("https://spdf.gsfc.nasa.gov/skteditor/index.html").read().decode("utf-8")
match = re.search(r'href="([^"]*skteditor_[^"]*_amd64\.deb)"', html)
if not match:
    raise SystemExit(1)
url = match.group(1)
if not url.startswith("http"):
    if url.startswith("/"):
        url = "https://spdf.gsfc.nasa.gov" + url
    else:
        url = "https://spdf.gsfc.nasa.gov/skteditor/" + url
print(url)
PY
)"
if [[ -z "${skt_deb_url}" ]]; then
  echo "Unable to find a Debian/Ubuntu SKTEditor package at ${skt_index_url}" >&2
  exit 1
fi

curl -fsSL "${skt_deb_url}" -o "${install_root}/skteditor_amd64.deb"
dpkg-deb -x "${install_root}/skteditor_amd64.deb" "${skt_root}"

skteditor_jar_path="$(find "${skt_root}" -name spdfjavaClasses.jar -print | head -n 1)"
if [[ -z "${skteditor_jar_path}" ]]; then
  echo "Unable to locate spdfjavaClasses.jar in extracted SKTEditor package." >&2
  exit 1
fi

mkdir -p "$(dirname "${skteditor_jar_path}")/extensions"
cp "${cdfjava_jar_path}" "$(dirname "${skteditor_jar_path}")/extensions/"

cat >&3 <<EOF
export SPDF_SKTEDITOR_JAR="${skteditor_jar_path}"
export CDF_JAVA_JAR="${cdfjava_jar_path}"
export CDF_JNI_LIB="${cdf_jni_lib_dir}"
export CDF_LIB="${cdf_native_lib_dir}"
EOF
