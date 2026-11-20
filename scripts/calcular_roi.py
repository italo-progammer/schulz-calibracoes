"""Estudo de ROI da automação (AV05). Reproduz todas as contas do relatório.

    python scripts/calcular_roi.py                 # cenário base
    python scripts/calcular_roi.py --horas-tecnica 80 --certificados-ano 600

Fórmula do roteiro:  ROI % = (Economia Líquida - Investimento) / Investimento * 100
    Economia Bruta  = certificados/ano x (min_manual - min_auto) / 60 x custo_hora
    Economia Líquida = Economia Bruta - custo anual de operação (cloud = R$ 0,00 no Free Tier)
    Payback (meses) = Investimento / (Economia Líquida / 12)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass
class Premissas:
    certificados_ano: float = 91 / 238 * 365      # 91 certificados em 238 dias (Cert. 00091/2026)
    min_manual: float = 25.0                      # exemplo do roteiro
    min_auto: float = 2.0                         # exemplo do roteiro
    custo_hora: float = 60.0                      # ASSUMIDO: confirmar com a Schulz (R$/h técnica)
    investimento: float = 5400.0                  # ASSUMIDO: 90 h x R$ 60 (desenvolvimento + implantação)
    custo_operacao_ano: float = 0.0               # cloud no Free Tier

    def horas_manual(self): return self.certificados_ano * self.min_manual / 60
    def horas_auto(self): return self.certificados_ano * self.min_auto / 60
    def horas_economizadas(self): return self.horas_manual() - self.horas_auto()
    def custo_manual(self): return self.horas_manual() * self.custo_hora
    def custo_auto(self): return self.horas_auto() * self.custo_hora + self.custo_operacao_ano
    def economia_bruta(self): return self.horas_economizadas() * self.custo_hora
    def economia_liquida(self): return self.economia_bruta() - self.custo_operacao_ano
    def roi_pct(self): return (self.economia_liquida() - self.investimento) / self.investimento * 100
    def payback_meses(self):
        mensal = self.economia_liquida() / 12
        return float("inf") if mensal <= 0 else self.investimento / mensal
    def roi_3_anos_pct(self):
        return (3 * self.economia_liquida() - self.investimento) / self.investimento * 100


def resumo(p: Premissas) -> dict:
    return {"certificados_ano": p.certificados_ano, "horas_manual": p.horas_manual(),
            "horas_auto": p.horas_auto(), "horas_economizadas": p.horas_economizadas(),
            "custo_manual": p.custo_manual(), "custo_auto": p.custo_auto(),
            "economia_bruta": p.economia_bruta(), "economia_liquida": p.economia_liquida(),
            "investimento": p.investimento, "roi_pct": p.roi_pct(),
            "payback_meses": p.payback_meses(), "roi_3_anos_pct": p.roi_3_anos_pct()}


def _brl(v): return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--certificados-ano", type=float)
    ap.add_argument("--min-manual", type=float); ap.add_argument("--min-auto", type=float)
    ap.add_argument("--custo-hora", type=float); ap.add_argument("--investimento", type=float)
    ap.add_argument("--horas-tecnica", type=float, help="horas de projeto (investimento = horas x custo da hora)")
    a = ap.parse_args()
    p = Premissas()
    for campo in ("certificados_ano", "min_manual", "min_auto", "custo_hora", "investimento"):
        if getattr(a, campo) is not None:
            setattr(p, campo, getattr(a, campo))
    if a.horas_tecnica is not None:
        p.investimento = a.horas_tecnica * p.custo_hora
    r = resumo(p)
    print(f"Certificados/ano ........ {r['certificados_ano']:.1f}")
    print(f"Horas manual / auto ..... {r['horas_manual']:.1f} h / {r['horas_auto']:.1f} h  (economia {r['horas_economizadas']:.1f} h)")
    print(f"Custo manual / auto ..... {_brl(r['custo_manual'])} / {_brl(r['custo_auto'])}")
    print(f"Economia bruta (OPEX) ... {_brl(r['economia_bruta'])}")
    print(f"Economia liquida ........ {_brl(r['economia_liquida'])}")
    print(f"Investimento ............ {_brl(r['investimento'])}")
    print(f"ROI (1 ano) ............. {r['roi_pct']:.1f} %")
    print(f"ROI (3 anos) ............ {r['roi_3_anos_pct']:.1f} %")
    print(f"Payback ................. {r['payback_meses']:.1f} meses")


if __name__ == "__main__":
    main()
