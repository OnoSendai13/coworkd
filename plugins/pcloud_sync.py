"""
pCloud Sync plugin for Cowork

Synchronizes files between local workspace and pCloud storage.
Supports both REST API access and local symlink to pCloud Drive.

pCloud Drive on Windows -> mounted in WSL2 via /mnt/c
pCloud REST API -> for remote operations
"""

import asyncio
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, BinaryIO

from base import CoworkPlugin, CoworkContext, CoworkTool


class PCloudPlugin(CoworkPlugin):
    name = "pcloud_sync"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self.api_base = "https://eapi.pcloud.com"  # EU data center
        self.token: Optional[str] = None
        self.local_mount: Optional[Path] = None
        self._session = None

    async def on_start(self):
        """Initialize pCloud connection."""
        # Check for token
        token_file = Path("~/.cowork/pcloud_token").expanduser()
        if token_file.exists():
            self.token = token_file.read_text().strip()
            self.log.info("pCloud token loaded")
        else:
            self.log.warning("No pCloud token found. Create ~/.cowork/pcloud_token with your OAuth token.")

        # Check for local pCloud Drive mount (Windows)
        possible_mounts = [
            Path("/mnt/c/Users/laurent/pCloud"),  # typical pCloud sync folder
            Path("/mnt/p"),                        # if pCloud Drive uses P: letter
        ]

        for mount in possible_mounts:
            if mount.exists():
                self.local_mount = mount
                self.log.info(f"pCloud local mount found: {mount}")
                break

        if not self.local_mount:
            self.log.warning("No local pCloud mount found. Install pCloud Drive on Windows or set sync folder manually.")

        # Setup async HTTP session
        try:
            import aiohttp
            self._session = aiohttp.ClientSession()
        except ImportError:
            self.log.warning("aiohttp not installed. REST API features disabled. pip install aiohttp")

    async def on_stop(self):
        """Cleanup."""
        if self._session:
            await self._session.close()

    def _api_headers(self) -> dict:
        """Build API auth headers."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @CoworkTool(name="pcloud_status", description="Check pCloud connection status and storage info.")
    async def status(self) -> str:
        """Get pCloud account status."""
        if not self.token:
            # Try local mount
            if self.local_mount:
                return json.dumps({
                    "status": "local_mount",
                    "mount": str(self.local_mount),
                    "files": len(list(self.local_mount.rglob("*"))),
                }, indent=2)
            return json.dumps({"status": "no_token", "error": "No pCloud token configured"})

        if not self._session:
            return json.dumps({"status": "error", "error": "aiohttp not installed"})

        try:
            async with self._session.get(
                f"{self.api_base}/userinfo",
                headers=self._api_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("result") == 0:
                    return json.dumps({
                        "status": "connected",
                        "email": data.get("email"),
                        "quota": data.get("quota"),
                        "used": data.get("usedquota"),
                    }, indent=2)
                else:
                    return json.dumps({"status": "api_error", "error": data})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    @CoworkTool(name="pcloud_list", description="List files in a pCloud folder.")
    async def list_folder(self, folder_id: int = 0, path: str = "/") -> str:
        """List contents of a pCloud folder."""
        if self.local_mount:
            # Use local filesystem
            full_path = self.local_mount / path.lstrip("/")
            if full_path.exists() and full_path.is_dir():
                items = []
                for item in full_path.iterdir():
                    items.append({
                        "name": item.name,
                        "type": "folder" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                    })
                return json.dumps({"path": path, "items": items}, indent=2)
            return json.dumps({"error": f"Path not found: {path}"})

        if not self._session or not self.token:
            return json.dumps({"error": "Not connected to pCloud"})

        try:
            async with self._session.get(
                f"{self.api_base}/listfolder",
                params={"folderid": folder_id},
                headers=self._api_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("result") == 0:
                    files = data.get("metadata", {}).get("files", [])
                    return json.dumps({"folder_id": folder_id, "files": files}, indent=2)
                return json.dumps({"error": data})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="pcloud_upload", description="Upload a file to pCloud.")
    async def upload(self, local_path: str, remote_path: str = "/") -> str:
        """Upload a file to pCloud."""
        local = Path(local_path).expanduser()
        if not local.exists():
            return json.dumps({"error": f"File not found: {local_path}"})

        if self.local_mount:
            # Copy to local mount
            dest = self.local_mount / remote_path.lstrip("/") / local.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(local, dest)
            return json.dumps({
                "status": "copied",
                "source": str(local),
                "dest": str(dest),
            })

        if not self._session or not self.token:
            return json.dumps({"error": "Not connected to pCloud"})

        # REST API upload
        try:
            with open(local, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("access_token", self.token)
                form.add_field("path", remote_path)
                form.add_field("file", f, filename=local.name)

                async with self._session.post(
                    f"{self.api_base}/uploadfile",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    data = await resp.json()
                    return json.dumps(data, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="pcloud_download", description="Download a file from pCloud.")
    async def download(self, remote_path: str, local_path: str) -> str:
        """Download a file from pCloud to local."""
        local = Path(local_path).expanduser()
        local.parent.mkdir(parents=True, exist_ok=True)

        if self.local_mount:
            # Copy from local mount
            source = self.local_mount / remote_path.lstrip("/")
            if source.exists():
                import shutil
                shutil.copy2(source, local)
                return json.dumps({
                    "status": "copied",
                    "source": str(source),
                    "dest": str(local),
                })
            return json.dumps({"error": f"Remote file not found: {remote_path}"})

        if not self._session or not self.token:
            return json.dumps({"error": "Not connected to pCloud"})

        try:
            # Get file ID first
            async with self._session.get(
                f"{self.api_base}/stat",
                params={"path": remote_path},
                headers=self._api_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("result") != 0:
                    return json.dumps({"error": data})
                file_id = data.get("metadata", {}).get("fileid")

            # Download
            async with self._session.get(
                f"{self.api_base}/downloadfile",
                params={"fileid": file_id},
                headers=self._api_headers(),
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    with open(local, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                    return json.dumps({
                        "status": "downloaded",
                        "dest": str(local),
                        "size": local.stat().st_size,
                    })
                return json.dumps({"error": f"HTTP {resp.status}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="pcloud_sync_workspace", description="Sync workspace folder to pCloud.")
    async def sync_workspace(self, remote_folder: str = "/cowork") -> str:
        """Sync workspace to pCloud."""
        workspace = self.ctx.workspace
        synced = []
        errors = []

        for item in workspace.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(workspace)
                remote = f"{remote_folder}/{rel_path}"

                try:
                    result = await self.upload(str(item), remote_folder)
                    result_data = json.loads(result)
                    if "error" not in result_data:
                        synced.append(str(rel_path))
                    else:
                        errors.append({"file": str(rel_path), "error": result_data["error"]})
                except Exception as e:
                    errors.append({"file": str(rel_path), "error": str(e)})

        return json.dumps({
            "synced": len(synced),
            "errors": len(errors),
            "files": synced,
            "errors_detail": errors,
        }, indent=2)
