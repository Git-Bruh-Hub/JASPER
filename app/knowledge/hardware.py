"""Small local catalog of verified, stable hardware specifications.

This is intentionally deterministic: the language model does not get to rewrite
these facts. Sources are recorded with the profile so the data can be refreshed
later by a dedicated web-research/update workflow.
"""
from __future__ import annotations

import re
from typing import Any

CPU_PROFILES: dict[str, dict[str, Any]] = {
    "amd ryzen 5 5600x": {
        "model": "AMD Ryzen 5 5600X",
        "architecture": "Zen 3",
        "cores": 6,
        "threads": 12,
        "threading": "AMD SMT (Simultaneous Multithreading)",
        "base_clock_ghz": 3.7,
        "max_boost_clock_ghz": 4.6,
        "l2_cache_mb": 3,
        "l3_cache_mb": 32,
        "total_cache_mb": 35,
        "tdp_w": 65,
        "socket": "AM4",
        "process_node": "TSMC 7nm FinFET",
        "pcie": "PCIe 4.0",
        "memory_type": "DDR4",
        "memory_speed": "up to 3200 MT/s",
        "integrated_graphics": False,
        "max_temperature_c": 95,
        "source": "AMD official product specification",
        "source_url": "https://www.amd.com/en/products/processors/desktops/ryzen/5000-series/amd-ryzen-5-5600x.html",
    },
}


def get_cpu_profile(cpu_name: str | None) -> dict[str, Any] | None:
    """Return a copy of a verified profile when the exact CPU model is recognized."""
    normalized = re.sub(r"[^a-z0-9]+", " ", str(cpu_name or "").lower()).strip()
    for key, profile in CPU_PROFILES.items():
        if key in normalized:
            return dict(profile)
    return None


def _wants_bm(question: str) -> bool:
    text = question.lower()
    return any(token in text for token in (
        "bahasa melayu", "bahasa malaysia", "dalam bm", "in bm", "dalam bahasa melayu",
        "apa fungsi", "macam mana", "menerangkan", "terangkan", "jelaskan",
    ))


def _is_detailed(question: str) -> bool:
    text = question.lower()
    return any(token in text for token in (
        "in detail", "detailed", "thorough", "comprehensive", "deep dive", "step by step", "explain fully",
    ))


def render_cpu_explanation(question: str, system_info: dict[str, Any]) -> str | None:
    """Render a deterministic CPU explanation for a recognized exact CPU model."""
    profile = get_cpu_profile(system_info.get("cpu"))
    if not profile:
        return None

    bm = _wants_bm(question)
    detailed = _is_detailed(question)
    cpu_name = profile["model"]

    if bm:
        lines = [
            f"CPU anda ialah **{cpu_name}**.",
            "\nCPU ialah komponen yang menjalankan arahan program dan melakukan pengiraan utama komputer. Secara mudah, ia membaca arahan, memproses data, dan menghasilkan keputusan yang diperlukan oleh sistem serta aplikasi.",
            "\nDalam penggunaan harian, CPU membantu menjalankan Windows, aplikasi, browser, emulator, game, dan proses latar belakang. CPU juga bekerjasama dengan RAM untuk data yang sedang digunakan dan dengan GPU untuk kerja grafik serta beban kerja yang sesuai.",
            f"\nCPU anda mempunyai **{profile['cores']} core fizikal dan {profile['threads']} thread** menggunakan **AMD SMT (Simultaneous Multithreading)**. Ini membolehkan sistem menjadualkan lebih banyak kerja serentak berbanding hanya melihat jumlah core fizikal.",
            f"\nKelajuan asas CPU ini ialah **{profile['base_clock_ghz']:.1f} GHz**, manakala **maximum boost** ialah sehingga **{profile['max_boost_clock_ghz']:.1f} GHz**. 3.7 GHz ialah base clock, bukan boost clock.",
        ]
    else:
        lines = [
            f"Your CPU is **{cpu_name}**.",
            "\nA CPU is the general-purpose processor that executes program instructions and performs the calculations needed by the operating system and applications. In simple terms, it repeatedly reads instructions, works on data, and produces results.",
            "\nFor your PC, the CPU is involved in running Windows, applications, browsers, games, background services, and other software. It also works closely with RAM for data currently in use and with the GPU for graphics workloads and other tasks that can be offloaded.",
            f"\nYour CPU has **{profile['cores']} physical cores and {profile['threads']} threads** using **AMD SMT (Simultaneous Multithreading)**. The 12-thread figure does not mean you have 12 physical cores, and AMD SMT is not Intel Hyper-Threading.",
            f"\nIts **base clock is {profile['base_clock_ghz']:.1f} GHz** and its **maximum boost clock is up to {profile['max_boost_clock_ghz']:.1f} GHz**. These are different specifications: 3.7 GHz is the base clock, while 4.6 GHz is the advertised maximum boost clock.",
        ]

    if detailed:
        if bm:
            lines.extend([
                "\n### Spesifikasi yang disahkan",
                f"| Spesifikasi | Nilai |\n|---|---|\n| Model | {cpu_name} |\n| Architecture | {profile['architecture']} |\n| Core / Thread | {profile['cores']} / {profile['threads']} |\n| Threading | AMD SMT |\n| Base Clock | {profile['base_clock_ghz']:.1f} GHz |\n| Maximum Boost | Up to {profile['max_boost_clock_ghz']:.1f} GHz |\n| L2 Cache | {profile['l2_cache_mb']} MB |\n| L3 Cache | {profile['l3_cache_mb']} MB |\n| TDP | {profile['tdp_w']} W |\n| Socket | {profile['socket']} |",
                "\n### Kitaran kerja CPU",
                "1. **Fetch** — mengambil arahan daripada memory.\n2. **Decode** — menentukan maksud arahan tersebut.\n3. **Execute** — melakukan operasi yang diperlukan.\n4. **Write back** — menyimpan atau meneruskan hasil untuk digunakan oleh sistem.",
                "\nNota: penggunaan RAM semasa komputer berjalan ialah **keadaan sistem semasa**, bukan spesifikasi CPU, jadi ia tidak dimasukkan ke dalam jadual CPU.",
            ])
        else:
            lines.extend([
                "\n### Verified specifications",
                f"| Specification | Value |\n|---|---|\n| Model | {cpu_name} |\n| Architecture | {profile['architecture']} |\n| Core / Thread | {profile['cores']} / {profile['threads']} |\n| Threading | AMD SMT |\n| Base Clock | {profile['base_clock_ghz']:.1f} GHz |\n| Maximum Boost | Up to {profile['max_boost_clock_ghz']:.1f} GHz |\n| L2 Cache | {profile['l2_cache_mb']} MB |\n| L3 Cache | {profile['l3_cache_mb']} MB |\n| TDP | {profile['tdp_w']} W |\n| Socket | {profile['socket']} |\n| PCIe | {profile['pcie']} |\n| Memory | {profile['memory_type']}, {profile['memory_speed']} |",
                "\n### CPU instruction cycle",
                "1. **Fetch** — obtains an instruction from memory.\n2. **Decode** — interprets what the instruction requires.\n3. **Execute** — performs the requested operation.\n4. **Write back** — stores or forwards the result.",
                "\nRAM usage is intentionally not listed as a CPU specification because it is a live system-state measurement, not a property of the processor model.",
            ])

    lines.append(f"\nSource: {profile['source']}." if not bm else f"\nSumber: {profile['source']}.")
    return "".join(lines)
