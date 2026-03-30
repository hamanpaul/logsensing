"""BDK 平台 profile — 提取自現有 hardcoded 預設值."""

from __future__ import annotations

from logsensing.platform.base import (
    ChannelDef,
    DrainOverride,
    MilestoneDef,
    PlatformProfile,
)

BDK_PROFILE = PlatformProfile(
    name="bdk",
    display_name="BDK (BGW720-300)",
    # --- Boot cycle ---
    boot_anchors=["U-Boot TPL"],
    fallback_anchors=["Starting kernel", "Booting Linux"],
    # --- Timestamp ---
    timestamp_pattern=r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]",
    timestamp_format="%Y-%m-%d %H:%M:%S.%f",
    supports_timing=True,
    # --- Milestones (baseline profiler) ---
    milestones=[
        MilestoneDef(name="tpl_start", pattern="U-Boot TPL", expected_order=1),
        MilestoneDef(name="uboot_main", pattern="U-Boot 2024", expected_order=2),
        MilestoneDef(
            name="watchdog_start",
            pattern="WDT:   Started watchdog",
            expected_order=3,
        ),
        MilestoneDef(name="kernel_start", pattern="Starting kernel", expected_order=4),
        MilestoneDef(
            name="linux_boot",
            pattern="Booting Linux on physical CPU",
            expected_order=5,
        ),
        MilestoneDef(
            name="rpc_tunnel_done",
            pattern="Init complete for FIFO tunnel",
            expected_order=6,
        ),
        MilestoneDef(
            name="pcie_link_up", pattern="bcm-pcie: Core", expected_order=7
        ),
        MilestoneDef(
            name="network_config", pattern="Configuring networking", expected_order=8
        ),
        MilestoneDef(
            name="enet_ready", pattern="wait_enet_ready done", expected_order=9
        ),
        MilestoneDef(
            name="wifi_fw_load",
            pattern="dhd_bus_start_try download fw",
            expected_order=10,
        ),
    ],
    # --- Reporter processes ---
    processes=[
        ("U-Boot TPL", "U-Boot TPL"),
        ("U-Boot Main", "U-Boot 2024"),
        ("Kernel Start", "Starting kernel"),
        ("Linux Boot", "Booting Linux on physical CPU"),
        ("SMCOS", "SMCOS:"),
        ("RPC Tunnel", "Init complete for FIFO tunnel"),
        ("Flow Cache", "fcache"),
        ("PCIe Link UP", "Link UP"),
        ("Networking Config", "Configuring networking"),
        ("WiFi wl0", "wl0:"),
        ("Enet Ready", "wait_enet_ready done"),
        ("DHD FW Load", "dhd_bus_start_try download fw"),
        ("Offload (dol0)", "dol0:"),
        ("SBF", "SBF:"),
        ("WiFi wl1", "wl1:"),
        ("WiFi wl2", "wl2:"),
        ("ACS Daemon", "acsd:"),
    ],
    # --- Demux channels ---
    demux_channels=[
        ChannelDef(
            name="wifi",
            patterns=["wl0", "wl1", "wl2", "CFG80211", "acsd"],
        ),
        ChannelDef(
            name="dhd",
            patterns=[r"dhd.*", r"dhdpcie.*"],
            is_regex=True,
        ),
        ChannelDef(
            name="rpc",
            patterns=["RPC", "ARMTF RPC"],
        ),
        ChannelDef(
            name="pcie",
            patterns=[r"bcm-pcie", r"pci\s"],
            is_regex=True,
        ),
        ChannelDef(
            name="network",
            patterns=[r"tc_netdev.*", "br0", "NET", "IPv6", r"e1000e", r"ixgbe"],
            is_regex=True,
        ),
        ChannelDef(
            name="kernel",
            patterns=["SMCOS", "SBF", "printk", "kfence"],
        ),
        ChannelDef(
            name="offload",
            patterns=["dol0", "dol1", "dol2", "fcache"],
        ),
    ],
    # --- Drain config ---
    drain_config=DrainOverride(
        sim_th=0.4,
        depth=4,
        max_clusters=1024,
        extra_delimiters=[":", "=", "|"],
    ),
    # --- Auto-detection ---
    detect_patterns=[
        "acsd:",
        "wait_enet_ready done",
        "dhd_bus_start_try download fw",
        "Configuring networking",
        "SBF:",
    ],
)
