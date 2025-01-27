"""Utility to run shell commands asynchronously with a timeout."""

import asyncio
import os
import signal
from typing import Tuple, Optional

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"
MAX_RESPONSE_LEN: int = 16000


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN) -> str:
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


async def run(
    cmd: str,
    timeout: float | None = 120.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
) -> Tuple[int, str, str]:
    """Run a shell command asynchronously with a timeout."""
    # Use zsh if available, otherwise fall back to bash
    shell = "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/bash"
    
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        shell=True,
        executable=shell,
        # Set process group for proper cleanup
        preexec_fn=os.setsid
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return (
            process.returncode or 0,
            maybe_truncate(stdout.decode(), truncate_after=truncate_after),
            maybe_truncate(stderr.decode(), truncate_after=truncate_after),
        )
    except asyncio.TimeoutError as exc:
        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            # Wait briefly for graceful shutdown
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                # Force kill if still running
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass  # Process already terminated
        raise TimeoutError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc
