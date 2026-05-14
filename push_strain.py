import base64
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_CYCLE_URL = "https://api.prod.whoop.com/developer/v2/cycle"
TIDBYT_PUSH_URL = "https://api.tidbyt.com/v0/devices/{device_id}/push"
INSTALLATION_ID = "whoopstrain"

GITHUB_REPO = "post-michael-r/whoop-tidbyt"
GITHUB_SECRET_NAME = "WHOOP_REFRESH_TOKEN"

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
STAR_PATH = ROOT / "strain.star"
WEBP_PATH = ROOT / "strain.webp"


def soft_exit(msg):
    print(msg)
    sys.exit(0)


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def update_env_refresh_token(env_path, new_value):
    with open(env_path) as f:
        lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("WHOOP_REFRESH_TOKEN=") or stripped.startswith("WHOOP_REFRESH_TOKEN ="):
            indent = line[: len(line) - len(stripped)]
            new_lines.append(f"{indent}WHOOP_REFRESH_TOKEN={new_value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"WHOOP_REFRESH_TOKEN={new_value}\n")

    tmp_path = str(env_path) + ".tmp"
    with open(tmp_path, "w") as f:
        f.writelines(new_lines)
    os.replace(tmp_path, env_path)


def update_github_secret_refresh_token(new_value):
    gh_pat = os.environ.get("GH_PAT")
    if not gh_pat:
        fail("GH_PAT not set; cannot rotate refresh token secret in GitHub Actions mode.")

    from nacl.encoding import Base64Encoder
    from nacl.public import PublicKey, SealedBox

    headers = {
        "Authorization": f"Bearer {gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    pk_resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    if pk_resp.status_code != 200:
        fail(f"GitHub public-key fetch HTTP {pk_resp.status_code}: {pk_resp.text}")
    pk = pk_resp.json()

    sealed = SealedBox(PublicKey(pk["key"].encode("ascii"), encoder=Base64Encoder))
    encrypted = sealed.encrypt(new_value.encode("utf-8"))

    put_resp = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/{GITHUB_SECRET_NAME}",
        headers=headers,
        json={
            "encrypted_value": base64.b64encode(encrypted).decode("ascii"),
            "key_id": pk["key_id"],
        },
        timeout=30,
    )
    if put_resp.status_code not in (201, 204):
        fail(f"GitHub secret update HTTP {put_resp.status_code}: {put_resp.text}")


def persist_refresh_token(new_value):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        update_github_secret_refresh_token(new_value)
    else:
        update_env_refresh_token(ENV_PATH, new_value)


def main():
    load_dotenv(ENV_PATH)
    client_id = os.environ.get("WHOOP_CLIENT_ID")
    client_secret = os.environ.get("WHOOP_CLIENT_SECRET")
    refresh_token = os.environ.get("WHOOP_REFRESH_TOKEN")
    device_id = os.environ.get("TIDBYT_DEVICE_ID")
    api_key = os.environ.get("TIDBYT_API_KEY")

    missing = [
        k for k, v in {
            "WHOOP_CLIENT_ID": client_id,
            "WHOOP_CLIENT_SECRET": client_secret,
            "WHOOP_REFRESH_TOKEN": refresh_token,
            "TIDBYT_DEVICE_ID": device_id,
            "TIDBYT_API_KEY": api_key,
        }.items() if not v
    ]
    if missing:
        fail(f"Missing in .env: {', '.join(missing)}")

    pixlet = shutil.which("pixlet") or os.path.expanduser("~/.local/bin/pixlet")
    if not (os.path.isfile(pixlet) and os.access(pixlet, os.X_OK)):
        fail("pixlet binary not found on PATH or at ~/.local/bin/pixlet")

    try:
        token_resp = requests.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "offline",
            },
            timeout=30,
        )
    except requests.RequestException as e:
        soft_exit(f"Whoop token refresh request failed: {e}")
    if token_resp.status_code != 200:
        soft_exit(f"Whoop token refresh HTTP {token_resp.status_code}: {token_resp.text}")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    new_refresh = tokens.get("refresh_token")
    if not access_token:
        soft_exit(f"No access_token in Whoop response: {tokens}")

    if new_refresh and new_refresh != refresh_token:
        persist_refresh_token(new_refresh)
        print("Refresh token rotated")

    try:
        cycle_resp = requests.get(
            WHOOP_CYCLE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"limit": 1},
            timeout=30,
        )
    except requests.RequestException as e:
        soft_exit(f"Whoop cycle fetch request failed: {e}")
    if cycle_resp.status_code != 200:
        soft_exit(f"Whoop cycle fetch HTTP {cycle_resp.status_code}: {cycle_resp.text}")

    data = cycle_resp.json()
    records = data.get("records") or []
    if not records:
        soft_exit("No cycles returned by Whoop; nothing to push.")

    latest = records[0]
    score_state = latest.get("score_state")
    if score_state != "SCORED":
        soft_exit(f"Latest cycle score_state is {score_state!r}; nothing to push.")

    score = latest.get("score")
    if score is None:
        soft_exit("Latest cycle has no score yet; nothing to push.")

    strain = score.get("strain")
    if strain is None or isinstance(strain, bool) or not isinstance(strain, (int, float)):
        soft_exit(f"Strain value missing or non-numeric ({strain!r}); nothing to push.")

    strain_str = f"{strain:.1f}"

    proc = subprocess.run(
        [
            pixlet, "render", str(STAR_PATH),
            f"strain={strain_str}",
            "--output", str(WEBP_PATH),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(f"pixlet render failed (exit {proc.returncode}):\n{proc.stderr or proc.stdout}")
    if not WEBP_PATH.exists():
        fail("pixlet render reported success but produced no output file.")

    webp_bytes = WEBP_PATH.read_bytes()
    payload = {
        "deviceID": device_id,
        "image": base64.b64encode(webp_bytes).decode("ascii"),
        "installationID": INSTALLATION_ID,
        "background": True,
    }
    push_resp = requests.post(
        TIDBYT_PUSH_URL.format(device_id=device_id),
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if push_resp.status_code != 200:
        fail(f"Tidbyt push HTTP {push_resp.status_code}: {push_resp.text}")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Pushed strain {strain_str} to Tidbyt at {ts}")


if __name__ == "__main__":
    main()
