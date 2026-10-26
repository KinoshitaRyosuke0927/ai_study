"""単元7(母比率・母分散・相関係数の区間推定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u07_var_ci.png : 母分散の 95% 信頼区間(n = 10、s² = 4)が s² に対して左右非対称になる様子
- u07_fisher.png : フィッシャーの z 変換(r = tanh z)と、z で対称な区間が r では非対称になる様子
"""
import math

import numpy as np
from scipy import stats

# ---------- 母分散の信頼区間 ----------
lo, hi = 36 / stats.chi2.ppf(0.975, 9), 36 / stats.chi2.ppf(0.025, 9)
fig, ax = plt.subplots(figsize=(10, 2.2))
ax.plot([lo, hi], [0, 0], color=PRIMARY, linewidth=4)
ax.plot(4, 0, "o", color=ACCENT, markersize=9, zorder=3)
ax.annotate(f"s2 = 4", xy=(4, 0), xytext=(4, 0.5), ha="center", color=ACCENT)
ax.annotate(f"lower {lo:.2f}", xy=(lo, 0), xytext=(lo, -0.6), ha="center")
ax.annotate(f"upper {hi:.2f}", xy=(hi, 0), xytext=(hi, -0.6), ha="center")
ax.set_xlim(0, 15)
ax.set_ylim(-1, 1)
ax.set_yticks([])
ax.set_xlabel("population variance")
ax.set_title("95% confidence interval for the variance is not symmetric around s2")
fig.tight_layout()
fig.savefig("u07_var_ci.png")
plt.close(fig)

# ---------- フィッシャーの z 変換 ----------
z = np.linspace(-0.2, 1.4, 300)
z0, se = math.atanh(0.6), 0.2
zl, zh = z0 - 1.96 * se, z0 + 1.96 * se
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(z, np.tanh(z), color=PRIMARY, linewidth=2, label="r = tanh(z)")
for zz, label in [(zl, f"{math.tanh(zl):.3f}"), (z0, "0.6"), (zh, f"{math.tanh(zh):.3f}")]:
    ax.plot([zz, zz], [-0.25, math.tanh(zz)], color="gray", linestyle=":", linewidth=1)
    ax.plot([-0.2, zz], [math.tanh(zz), math.tanh(zz)], color="gray", linestyle=":", linewidth=1)
    ax.text(-0.18, math.tanh(zz) + 0.02, label, fontsize=9)
ax.plot([zl, zh], [-0.2, -0.2], color=ACCENT, linewidth=4, label="interval in z (symmetric)")
ax.plot([-0.15, -0.15], [math.tanh(zl), math.tanh(zh)], color=ACCENT, linewidth=4, alpha=0.6, label="interval in r (not symmetric)")
ax.set_xlim(-0.2, 1.4)
ax.set_ylim(-0.25, 1.0)
ax.set_xlabel("z = arctanh(r)")
ax.set_ylabel("r")
ax.legend(loc="lower right", fontsize=8)
fig.tight_layout()
fig.savefig("u07_fisher.png")
plt.close(fig)
print("done")
