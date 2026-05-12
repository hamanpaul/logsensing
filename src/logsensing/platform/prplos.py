"""prplOS 平台 profile."""

from __future__ import annotations

from logsensing.analyzer.detector import AnomalyRule
from logsensing.platform.base import (
    ChannelDef,
    DrainOverride,
    MilestoneDef,
    PlatformProfile,
)

PRPLOS_PROFILE = PlatformProfile(
    name="prplos",
    display_name="prplOS (BGW720-300)",
    # --- Boot cycle ---
    boot_anchors=["U-Boot TPL"],
    fallback_anchors=["Starting kernel", "Booting Linux"],
    # --- Timestamp ---
    # prplOS serial console logs 通常無 host-side timestamp
    timestamp_pattern=None,
    timestamp_format=None,
    supports_timing=False,
    # --- Milestones (baseline profiler) ---
    milestones=[
        MilestoneDef(name="smc_bootloader", pattern="SMC bootloader", expected_order=1),
        MilestoneDef(name="smc_os_loaded", pattern="SMC OS loaded successfully", expected_order=2),
        MilestoneDef(name="smcos_start", pattern="SMCOS: starting core services", expected_order=3),
        MilestoneDef(name="tpl_start", pattern="U-Boot TPL", expected_order=4),
        MilestoneDef(name="uboot_main", pattern="U-Boot 2024", expected_order=5),
        MilestoneDef(
            name="watchdog_start",
            pattern="WDT:   Started watchdog",
            expected_order=6,
        ),
        MilestoneDef(name="kernel_start", pattern="Starting kernel", expected_order=7),
        MilestoneDef(
            name="linux_boot",
            pattern="Booting Linux on physical CPU",
            expected_order=8,
        ),
        MilestoneDef(
            name="rpc_tunnel_done",
            pattern="Init complete for FIFO tunnel",
            expected_order=9,
        ),
        MilestoneDef(
            name="procd_early", pattern="procd: - early -", expected_order=10
        ),
        MilestoneDef(
            name="procd_ubus", pattern="procd: - ubus -", expected_order=11
        ),
        MilestoneDef(
            name="procd_init", pattern="procd: - init -", expected_order=12
        ),
        MilestoneDef(
            name="kmodloader", pattern="kmodloader: done loading", expected_order=13
        ),
        MilestoneDef(
            name="pcie_link_up", pattern="bcm-pcie: Core", expected_order=14
        ),
        MilestoneDef(
            name="wlan_modules",
            pattern="loading WLAN kernel modules",
            expected_order=15,
        ),
        MilestoneDef(name="wifi_wl0_init", pattern="wl0: creating kthread", expected_order=16),
        MilestoneDef(name="wifi_wl1_init", pattern="wl1: creating kthread", expected_order=17),
        MilestoneDef(name="wifi_wl2_init", pattern="wl2: creating kthread", expected_order=18),
    ],
    # --- Reporter processes ---
    processes=[
        ("SMC Bootloader", "SMC bootloader"),
        ("SMC OS", "SMC OS loaded"),
        ("SMCOS Services", "SMCOS: starting core services"),
        ("U-Boot TPL", "U-Boot TPL"),
        ("U-Boot Main", "U-Boot 2024"),
        ("Kernel Start", "Starting kernel"),
        ("Linux Boot", "Booting Linux on physical CPU"),
        ("RPC Tunnel", "Init complete for FIFO tunnel"),
        ("procd early", "procd: - early -"),
        ("procd ubus", "procd: - ubus -"),
        ("procd init", "procd: - init -"),
        ("kmodloader", "kmodloader: done loading"),
        ("PCIe Link UP", "bcm-pcie: Core"),
        ("WLAN Modules", "loading WLAN kernel modules"),
        ("WiFi wl0", "wl0: creating kthread"),
        ("WiFi wl1", "wl1: creating kthread"),
        ("WiFi wl2", "wl2: creating kthread"),
    ],
    # --- Demux channels ---
    demux_channels=[
        ChannelDef(
            name="wifi",
            patterns=["wl0", "wl1", "wl2", "CFG80211"],
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
            name="procd",
            patterns=["procd:", "ubusd", "netifd"],
        ),
        ChannelDef(
            name="tr181",
            patterns=[r"tr181-.*"],
            is_regex=True,
        ),
        ChannelDef(
            name="kernel",
            patterns=["SMCOS", "kmodloader", "printk", "kfence"],
        ),
        ChannelDef(
            name="network",
            patterns=[r"tc_netdev.*", "br0", "NET", "IPv6"],
            is_regex=True,
        ),
        ChannelDef(
            name="offload",
            patterns=["dol0", "dol1", "dol2", "fcache"],
        ),
    ],
    anomaly_rules=[
        AnomalyRule(
            rule_id="boot_timeout",
            name="Boot Timeout",
            severity="critical",
            rule_type="pattern",
            pattern="Boot timeout",
        ),
        AnomalyRule(
            rule_id="phy_lookup_failed",
            name="PHY Lookup Failed",
            severity="warning",
            rule_type="pattern",
            pattern="Failed to find phy for port",
        ),
        AnomalyRule(
            rule_id="overlayfs_inode_failure",
            name="OverlayFS Inode Failure",
            severity="critical",
            rule_type="pattern",
            pattern="overlayfs: failed to get inode",
        ),
        AnomalyRule(
            rule_id="gpio_probe_failed",
            name="GPIO Expander Probe Failed",
            severity="warning",
            rule_type="pattern",
            pattern="pca953x: probe of",
        ),
        AnomalyRule(
            rule_id="watchdog_device_busy",
            name="Watchdog Device Busy",
            severity="warning",
            rule_type="pattern",
            pattern="Could not open /dev/watchdog",
        ),
        AnomalyRule(
            rule_id="regulatory_db_missing",
            name="Regulatory DB Missing",
            severity="warning",
            rule_type="pattern",
            pattern="failed to load regulatory.db",
        ),
        AnomalyRule(
            rule_id="cfg80211_error",
            name="CFG80211 Error",
            severity="warning",
            rule_type="pattern",
            pattern="CFG80211-ERROR",
        ),
        AnomalyRule(
            rule_id="fatal_signal",
            name="Unexpected Fatal Signal",
            severity="critical",
            rule_type="pattern",
            pattern="potentially unexpected fatal signal",
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
        "procd: - ubus -",
        "procd: - init -",
        "kmodloader:",
        "prplOS",
        "root@prplOS",
    ],
)
