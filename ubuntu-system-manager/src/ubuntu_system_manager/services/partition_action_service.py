from __future__ import annotations

from dataclasses import dataclass

from ubuntu_system_manager.models import PartitionEntry

from .command_runner import run_command, run_privileged_command

EXT_FILESYSTEMS = {"ext2", "ext3", "ext4"}
NTFS_FILESYSTEMS = {"ntfs", "ntfs3", "fuseblk"}
SPECIAL_MOUNTPOINT_PREFIX = "/media/hamad/other"
SPECIAL_TARGET_CANONICAL = "/media/hamad/Other"
SPECIAL_FALLBACK_DEVICE = "/dev/sda1"
SYSTEM_MOUNTPOINTS = {"/", "/boot", "/boot/efi"}


def _is_special_mountpoint(path: str) -> bool:
    return (path or "").strip().lower().startswith(SPECIAL_MOUNTPOINT_PREFIX)


@dataclass(slots=True)
class PartitionFixStepResult:
    ok: bool
    code: int
    step: str
    stdout: str
    stderr: str
    command: list[str]
    queue_wait_seconds: float
    execution_seconds: float


@dataclass(slots=True)
class PartitionFixResult:
    ok: bool
    message: str
    steps: list[PartitionFixStepResult]


class PartitionActionService:
    def mount_partition(self, partition: PartitionEntry) -> PartitionFixResult:
        steps: list[PartitionFixStepResult] = []
        device = partition.device
        filesystem = partition.filesystem.lower()
        mountpoint = partition.mountpoint if partition.mountpoint != "-" else ""
        expected_mountpoint = partition.expected_mountpoint if partition.expected_mountpoint != "-" else ""

        if not device or device == "-":
            return PartitionFixResult(False, "Invalid partition device.", steps)
        if mountpoint:
            return PartitionFixResult(False, f"Partition {device} is already mounted.", steps)
        if expected_mountpoint in SYSTEM_MOUNTPOINTS:
            return PartitionFixResult(False, "Refusing to mount to a protected system mountpoint.", steps)

        if expected_mountpoint:
            if _is_special_mountpoint(expected_mountpoint):
                special_target = SPECIAL_TARGET_CANONICAL
                special_steps = self._run_special_mount_fix(
                    device=device,
                    filesystem=filesystem,
                    target_mountpoint=special_target,
                )
                steps.extend(special_steps)
                if not special_steps or not special_steps[-1].ok:
                    return PartitionFixResult(False, f"Mount failed for {device}. Use Fix to repair.", steps)

                verify_target_step = self._verify_target_mounted_step(special_target)
                steps.append(verify_target_step)
                if not verify_target_step.ok:
                    return PartitionFixResult(
                        False,
                        (
                            f"Mount command completed but target is still not mounted ({special_target}). "
                            "Use Fix to repair."
                        ),
                        steps,
                    )
                return PartitionFixResult(True, f"Partition mounted successfully at {special_target}.", steps)

            mkdir_step = self._run_privileged_step(
                step=f"Ensure mountpoint directory {expected_mountpoint}",
                command=["mkdir", "-p", expected_mountpoint],
                timeout=120,
            )
            steps.append(mkdir_step)
            if not mkdir_step.ok:
                return PartitionFixResult(False, f"Failed to prepare mountpoint {expected_mountpoint}.", steps)

            mount_cmd, mount_step_name = self._build_mount_command(
                device=device,
                filesystem=filesystem,
                target_mountpoint=expected_mountpoint,
            )
            mount_step = self._run_privileged_step(
                step=mount_step_name,
                command=mount_cmd,
                timeout=300,
            )
            steps.append(mount_step)
            if not mount_step.ok:
                recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                    steps=steps,
                    device=device,
                    filesystem=filesystem,
                )
                if recovered:
                    return PartitionFixResult(True, recovery_message, steps)
                return PartitionFixResult(False, f"Mount failed for {device}. Use Fix to repair.", steps)
        else:
            mount_cmd, mount_step_name = self._build_mount_command(
                device=device,
                filesystem=filesystem,
                target_mountpoint="",
            )
            mount_step = self._run_privileged_step(
                step=mount_step_name,
                command=mount_cmd,
                timeout=300,
            )
            steps.append(mount_step)
            if not mount_step.ok:
                recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                    steps=steps,
                    device=device,
                    filesystem=filesystem,
                )
                if recovered:
                    return PartitionFixResult(True, recovery_message, steps)
                return PartitionFixResult(False, f"Mount failed for {device}. Use Fix to repair.", steps)

        verify_step = self._verify_mount_step(device=device, expected_mountpoint=expected_mountpoint)
        steps.append(verify_step)
        if not verify_step.ok:
            recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                steps=steps,
                device=device,
                filesystem=filesystem,
            )
            if recovered:
                return PartitionFixResult(True, recovery_message, steps)
            return PartitionFixResult(False, f"Mount command completed but partition is still not mounted ({device}).", steps)

        return PartitionFixResult(True, f"Partition {device} mounted successfully.", steps)

    def fix_partition(self, partition: PartitionEntry) -> PartitionFixResult:
        steps: list[PartitionFixStepResult] = []
        device = partition.device
        filesystem = partition.filesystem.lower()
        mountpoint = partition.mountpoint if partition.mountpoint != "-" else ""
        expected_mountpoint = partition.expected_mountpoint if partition.expected_mountpoint != "-" else ""
        mountpoint_lower = mountpoint.lower()
        expected_lower = expected_mountpoint.lower()

        if not device or device == "-":
            return PartitionFixResult(False, "Invalid partition device.", steps)

        if mountpoint in SYSTEM_MOUNTPOINTS or expected_mountpoint in SYSTEM_MOUNTPOINTS:
            return PartitionFixResult(
                False,
                f"Refusing to run automatic fix on system mountpoint ({mountpoint or expected_mountpoint}).",
                steps,
            )

        if _is_special_mountpoint(expected_lower) or _is_special_mountpoint(mountpoint_lower):
            special_target = SPECIAL_TARGET_CANONICAL
            special_fix_steps = self._run_special_mount_fix(
                device=device,
                filesystem=filesystem,
                target_mountpoint=special_target,
            )
            steps.extend(special_fix_steps)
            if not special_fix_steps or not special_fix_steps[-1].ok:
                return PartitionFixResult(False, f"Dedicated mount fix failed for {SPECIAL_TARGET_CANONICAL}.", steps)

            verify_target_step = self._verify_target_mounted_step(special_target)
            steps.append(verify_target_step)
            if not verify_target_step.ok:
                return PartitionFixResult(
                    False,
                    f"Dedicated mount fix ran, but target is still not mounted ({special_target}).",
                    steps,
                )
            return PartitionFixResult(True, "Partition fixed successfully via dedicated mount workflow.", steps)

        if mountpoint:
            unmount_step = self._run_privileged_step(
                step=f"Unmount {device}",
                command=["umount", device],
                timeout=300,
            )
            steps.append(unmount_step)
            if not unmount_step.ok:
                return PartitionFixResult(False, f"Unable to unmount {device} before repair.", steps)

        if filesystem in EXT_FILESYSTEMS:
            repair_step = self._run_privileged_step(
                step=f"Run fsck repair on {device}",
                command=["fsck", "-y", device],
                timeout=3600,
            )
            steps.append(repair_step)
            if not repair_step.ok:
                return PartitionFixResult(False, f"fsck repair failed on {device}.", steps)
        elif filesystem == "ntfs":
            repair_step = self._run_privileged_step(
                step=f"Run ntfsfix repair on {device}",
                command=["ntfsfix", device],
                timeout=3600,
            )
            steps.append(repair_step)
            if not repair_step.ok:
                recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                    steps=steps,
                    device=device,
                    filesystem=filesystem,
                )
                if recovered:
                    return PartitionFixResult(True, recovery_message, steps)
                return PartitionFixResult(False, f"ntfsfix repair failed on {device}.", steps)
        else:
            return PartitionFixResult(
                False,
                (
                    f"Unsupported filesystem '{partition.filesystem}' for automatic fix. "
                    "Use manual repair tools for this partition."
                ),
                steps,
            )

        remount_steps = self._attempt_remount_steps(device=device, expected_mountpoint=expected_mountpoint)
        steps.extend(remount_steps)
        for remount_step in remount_steps:
            if not remount_step.ok:
                recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                    steps=steps,
                    device=device,
                    filesystem=filesystem,
                )
                if recovered:
                    return PartitionFixResult(True, recovery_message, steps)
                return PartitionFixResult(False, f"Repair completed but remount failed for {device}.", steps)

        verify_step = self._verify_mount_step(device=device, expected_mountpoint=expected_mountpoint)
        steps.append(verify_step)
        if not verify_step.ok:
            recovered, recovery_message = self._attempt_ntfs_recovery_mount(
                steps=steps,
                device=device,
                filesystem=filesystem,
            )
            if recovered:
                return PartitionFixResult(True, recovery_message, steps)
            return PartitionFixResult(False, f"Repair completed but mount validation failed for {device}.", steps)

        return PartitionFixResult(True, f"Partition {device} fixed successfully.", steps)

    def _run_special_mount_fix(
        self,
        *,
        device: str,
        filesystem: str,
        target_mountpoint: str,
    ) -> list[PartitionFixStepResult]:
        steps: list[PartitionFixStepResult] = []
        mkdir_step = self._run_privileged_step(
            step=f"Ensure mountpoint directory {target_mountpoint}",
            command=["mkdir", "-p", target_mountpoint],
            timeout=120,
        )
        steps.append(mkdir_step)
        if not mkdir_step.ok:
            return steps

        candidate_devices: list[str] = []
        for candidate in [device, SPECIAL_FALLBACK_DEVICE]:
            if candidate and candidate not in candidate_devices:
                candidate_devices.append(candidate)

        for idx, candidate_device in enumerate(candidate_devices, start=1):
            mount_cmd = ["mount", "-t", "ntfs-3g", candidate_device, target_mountpoint]
            mount_step_name = f"Mount {candidate_device} to {target_mountpoint} with ntfs-3g"
            if candidate_device != device:
                mount_step_name = f"{mount_step_name} (fallback #{idx})"

            mount_step = self._run_privileged_step(
                step=mount_step_name,
                command=mount_cmd,
                timeout=300,
            )
            steps.append(mount_step)
            if mount_step.ok:
                break
        return steps

    def _attempt_ntfs_recovery_mount(
        self,
        *,
        steps: list[PartitionFixStepResult],
        device: str,
        filesystem: str,
    ) -> tuple[bool, str]:
        filesystem_normalized = (filesystem or "").strip().lower()
        if filesystem_normalized not in NTFS_FILESYSTEMS and filesystem_normalized not in {"", "-", "unknown"}:
            return False, ""

        recovery_steps = self._run_special_mount_fix(
            device=device,
            filesystem=filesystem,
            target_mountpoint=SPECIAL_TARGET_CANONICAL,
        )
        steps.extend(recovery_steps)
        if not recovery_steps or not recovery_steps[-1].ok:
            return False, f"NTFS fallback mount failed for {device}."

        verify_target_step = self._verify_target_mounted_step(SPECIAL_TARGET_CANONICAL)
        steps.append(verify_target_step)
        if not verify_target_step.ok:
            return False, f"NTFS fallback mounted command ran, but target is still unavailable ({SPECIAL_TARGET_CANONICAL})."

        return True, f"Partition recovered via fallback mount at {SPECIAL_TARGET_CANONICAL}."

    def _attempt_remount_steps(self, *, device: str, expected_mountpoint: str) -> list[PartitionFixStepResult]:
        steps: list[PartitionFixStepResult] = []
        if expected_mountpoint:
            mkdir_step = self._run_privileged_step(
                step=f"Ensure mountpoint directory {expected_mountpoint}",
                command=["mkdir", "-p", expected_mountpoint],
                timeout=120,
            )
            steps.append(mkdir_step)
            if not mkdir_step.ok:
                return steps

            mount_step = self._run_privileged_step(
                step=f"Mount {device} to {expected_mountpoint}",
                command=["mount", device, expected_mountpoint],
                timeout=300,
            )
            steps.append(mount_step)
            return steps

        mount_step = self._run_privileged_step(
            step=f"Mount {device}",
            command=["mount", device],
            timeout=300,
        )
        steps.append(mount_step)
        return steps

    def _verify_mount_step(self, *, device: str, expected_mountpoint: str) -> PartitionFixStepResult:
        result = run_command(["findmnt", "-rn", "-S", device, "-o", "TARGET"], timeout=15)
        targets = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if expected_mountpoint:
            ok = expected_mountpoint in targets
            stderr = result.stderr
            if not ok and not stderr:
                stderr = f"Expected target not mounted: {expected_mountpoint}"
        else:
            ok = bool(targets)
            stderr = result.stderr
            if not ok and not stderr:
                stderr = "Partition is still not mounted."

        return PartitionFixStepResult(
            ok=ok and result.ok,
            code=result.code,
            step=f"Verify mount state for {device}",
            stdout=result.stdout,
            stderr=stderr,
            command=["findmnt", "-rn", "-S", device, "-o", "TARGET"],
            queue_wait_seconds=0.0,
            execution_seconds=0.0,
        )

    def _run_privileged_step(self, *, step: str, command: list[str], timeout: int) -> PartitionFixStepResult:
        result = run_privileged_command(command, timeout=timeout)
        return PartitionFixStepResult(
            ok=result.ok,
            code=result.code,
            step=step,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
            queue_wait_seconds=result.queue_wait_seconds,
            execution_seconds=result.execution_seconds,
        )

    def _verify_target_mounted_step(self, mountpoint: str) -> PartitionFixStepResult:
        result = run_command(["findmnt", "-rn", "-T", mountpoint, "-o", "SOURCE,TARGET"], timeout=15)
        ok = result.ok and bool(result.stdout.strip())
        stderr = result.stderr
        if not ok and not stderr:
            stderr = f"Target mountpoint is not mounted: {mountpoint}"
        return PartitionFixStepResult(
            ok=ok,
            code=result.code,
            step=f"Verify target mountpoint {mountpoint}",
            stdout=result.stdout,
            stderr=stderr,
            command=["findmnt", "-rn", "-T", mountpoint, "-o", "SOURCE,TARGET"],
            queue_wait_seconds=0.0,
            execution_seconds=0.0,
        )

    def _build_mount_command(self, *, device: str, filesystem: str, target_mountpoint: str) -> tuple[list[str], str]:
        if filesystem in NTFS_FILESYSTEMS:
            if target_mountpoint:
                return (
                    ["mount", "-t", "ntfs-3g", device, target_mountpoint],
                    f"Mount {device} to {target_mountpoint} with ntfs-3g",
                )
            return (["mount", "-t", "ntfs-3g", device], f"Mount {device} with ntfs-3g")
        if target_mountpoint:
            return (["mount", device, target_mountpoint], f"Mount {device} to {target_mountpoint}")
        return (["mount", device], f"Mount {device}")
