#!/usr/bin/env python3
"""
美国生产率 / 单位劳动力成本 追踪
用途：检验"劳动力供给归零 -> 滞胀 -> 联储被卡住"这条链是否成立。
数据源：FRED 公开 CSV 端点，无需 API key。
"""

import io
import sys
import urllib.request
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SERIES = {
    "ULCNFB":  "单位劳动力成本",
    "OPHNFB":  "每小时产出(劳动生产率)",
    "OUTNFB":  "实际产出",
    "HOANBS":  "总工时",
    "COMPNFB": "每小时薪酬",
    "DFII10":  "10年期TIPS实际收益率",
    "CLF16OV": "劳动力人口(千人)",
    "CIVPART": "劳动参与率",
}

# 判据门槛（单位劳动力成本四季度同比）
THRESH_CONFIRM = 3.0   # 站上 -> 滞胀链成立
THRESH_VOID    = 2.0   # 压在下方 -> 链条第三步断裂

CYCLE_START     = "2019-10-01"  # 本轮周期起点
PREV_CYCLE_FROM = "2007-10-01"
PREV_CYCLE_TO   = "2019-10-01"


def fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urllib.request.urlopen(url, timeout=30) as r:
        df = pd.read_csv(io.StringIO(r.read().decode()))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"]


def yoy(s: pd.Series, periods: int = 4) -> pd.Series:
    """同比变化（季度序列用 periods=4）。"""
    return (s / s.shift(periods) - 1) * 100


def annualized(s: pd.Series, start: str, end: str | None = None) -> float:
    """区间年化增速。"""
    w = s.loc[start:end] if end else s.loc[start:]
    quarters = len(w) - 1
    if quarters <= 0:
        return float("nan")
    return ((w.iloc[-1] / w.iloc[0]) ** (4 / quarters) - 1) * 100


def main() -> int:
    data = {}
    for sid in SERIES:
        try:
            data[sid] = fred(sid)
        except Exception as exc:
            print(f"[警告] {sid} 抓取失败：{exc}", file=sys.stderr)

    if "ULCNFB" not in data or "OPHNFB" not in data:
        print("核心序列缺失，中止。", file=sys.stderr)
        return 1

    ulc_yoy  = yoy(data["ULCNFB"])
    prod_yoy = yoy(data["OPHNFB"])
    out_yoy  = yoy(data["OUTNFB"])
    hrs_yoy  = yoy(data["HOANBS"])
    comp_yoy = yoy(data["COMPNFB"])

    q = ulc_yoy.index[-1]
    tag = f"{q.year}Q{(q.month - 1) // 3 + 1}"

    u, p = ulc_yoy.iloc[-1], prod_yoy.iloc[-1]
    o, h, c = out_yoy.iloc[-1], hrs_yoy.iloc[-1], comp_yoy.iloc[-1]

    print("=" * 62)
    print(f"美国生产率 / 单位劳动力成本追踪   最新季度 {tag}   跑于 {date.today()}")
    print("=" * 62)

    print(f"\n【主信号】单位劳动力成本 四季度同比：{u:+.2f}%")
    if u >= THRESH_CONFIRM:
        verdict = "滞胀链成立 —— 工资涨幅未被生产率吸收，联储降息空间受压"
    elif u <= THRESH_VOID:
        verdict = "链条第三步断裂 —— 生产率吸收住了工资，滞胀推论作废"
    else:
        verdict = "观察区 —— 尚未证实也未证伪，继续跟踪"
    print(f"  判定：{verdict}")
    print(f"  拆解：每小时薪酬 {c:+.2f}%  -  劳动生产率 {p:+.2f}%")

    print(f"\n【真伪校验】生产率是产出拉动还是工时萎缩造成的？")
    print(f"  实际产出同比 {o:+.2f}%   总工时同比 {h:+.2f}%")
    if h < 0 and o < 1.0:
        print("  ⚠ 分母驱动：工时在收缩而产出停滞，这轮生产率上升多半是构成效应，不是技术进步")
    elif o >= h:
        print("  ✓ 产出驱动：性质健康")
    else:
        print("  △ 混合：产出增速低于工时增速，留意")

    print(f"\n【周期对照】劳动生产率年化增速")
    print(f"  本轮周期 {CYCLE_START[:7]} 至今 ： {annualized(data['OPHNFB'], CYCLE_START):.2f}%")
    print(f"  上轮周期 2007Q4-2019Q4    ： "
          f"{annualized(data['OPHNFB'], PREV_CYCLE_FROM, PREV_CYCLE_TO):.2f}%")
    print("  两者之差就是 AI 是否兑现的全部实证痕迹")

    if "CLF16OV" in data:
        lf = data["CLF16OV"]
        print(f"\n【劳动力供给】劳动力人口最新 {lf.iloc[-1]:,.0f} 千人")
        print(f"  近6个月变化 {lf.iloc[-1] - lf.iloc[-7]:+,.0f} 千人"
              f"   参与率 {data['CIVPART'].iloc[-1]:.1f}%")

    if "DFII10" in data:
        print(f"\n【利率侧】10年期TIPS实际收益率 {data['DFII10'].iloc[-1]:.2f}%"
              f"（{data['DFII10'].index[-1].date()}）")

    # 图：单位劳动力成本同比 vs 10年期实际收益率
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    w = ulc_yoy.loc["2015":]
    ax1.plot(w.index, w.values, lw=2, color="#c0392b", label="ULC YoY (4q)")
    ax1.axhline(THRESH_CONFIRM, ls="--", lw=1, color="#c0392b", alpha=.5)
    ax1.axhline(THRESH_VOID, ls="--", lw=1, color="#27ae60", alpha=.5)
    ax1.axhspan(THRESH_VOID, THRESH_CONFIRM, color="grey", alpha=.08)
    ax1.set_ylabel("ULC YoY  (%)", color="#c0392b")
    ax1.axhline(0, lw=.8, color="black", alpha=.3)

    if "DFII10" in data:
        ax2 = ax1.twinx()
        r = data["DFII10"].loc["2015":].resample("QE").mean()
        ax2.plot(r.index, r.values, lw=1.6, color="#2c3e50", alpha=.8,
                 label="10y TIPS real yield")
        ax2.set_ylabel("10y real yield (%)", color="#2c3e50")

    ax1.set_title(f"ULC YoY vs 10y Real Yield   (latest {tag})")
    handles = ax1.get_legend_handles_labels()
    if "DFII10" in data:
        h2, l2 = ax2.get_legend_handles_labels()
        handles = (handles[0] + h2, handles[1] + l2)
    ax1.legend(*handles, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig("ulc_vs_real_yield.png", dpi=140)
    print("\n图已保存：ulc_vs_real_yield.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
