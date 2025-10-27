from __future__ import annotations
from typing import NamedTuple, List, Dict, Optional, Tuple, Callable

class Config(NamedTuple):
    principal: float
    periods: int
    rate: float
    late_fee_percent: float
    daily_mora_rate: float
    default_after_missed: int
    days_in_period: int = 30

class State(NamedTuple):
    t: int
    principal: float
    overdue: float
    status: str
    missed: int

class Decision(NamedTuple):
    will_pay: bool
    delay_days: int
    extra: float

def price_payment(pv: float, i: float, n: int) -> float:
    if n <= 0: raise ValueError("periods deve ser > 0")
    if i == 0: return pv / n
    f = (i * (1+i)**n) / ((1+i)**n - 1)
    return pv * f

def juros_periodo(principal: float, rate: float) -> float:
    return principal * rate

def encargos_atraso(parcela: float, atraso_dias: int, multa: float, mora_dia: float) -> float:
    if atraso_dias <= 0: return 0.0
    return parcela * multa + parcela * mora_dia * atraso_dias

def mora_sobre_vencido(vencido: float, mora_dia: float, dias: int) -> float:
    return 0.0 if vencido <= 0 else vencido * mora_dia * dias

def step(cfg: Config, st: State, dc: Decision, parcela: float) -> Tuple[State, Dict]:
    if st.status != "active":
        return st, {"period": st.t, "status": st.status}

    if dc.will_pay:
        j = juros_periodo(st.principal, cfg.rate)
        amort = max(0.0, parcela - j)
        new_principal = max(0.0, st.principal - amort - max(0.0, dc.extra))
        vencidos_mora = mora_sobre_vencido(st.overdue, cfg.daily_mora_rate, cfg.days_in_period)
        overdue_end = st.overdue + vencidos_mora
        late = encargos_atraso(parcela, dc.delay_days, cfg.late_fee_percent, cfg.daily_mora_rate)

        new_state = State(st.t+1, new_principal, overdue_end, "active", 0)
        row = dict(
            period=st.t, status=new_state.status,
            evento=("Pago em dia" if dc.delay_days==0 else f"Pago com {dc.delay_days}d de atraso"),
            paid=True, on_time=(dc.delay_days==0),
            delay_days=dc.delay_days, parcela=parcela, juros=j, amort=amort,
            extra=dc.extra, late=late,
            cash_out=parcela + late + max(0.0, dc.extra),
            principal_end=new_principal, overdue_end=overdue_end
        )

        if new_principal <= 1e-6 and overdue_end <= 1e-6:
            new_state = new_state._replace(status="paid")
            row["status"] = "paid"
            row["evento"] = "Contrato quitado"
        return new_state, row

    else:
        j = juros_periodo(st.principal, cfg.rate)
        added = parcela
        vencidos_mora = mora_sobre_vencido(st.overdue, cfg.daily_mora_rate, cfg.days_in_period)
        new_overdue = st.overdue + added + vencidos_mora
        missed = st.missed + 1
        status = "default" if missed >= cfg.default_after_missed else "active"

        new_state = State(st.t+1, st.principal, new_overdue, status, missed)
        row = dict(
            period=st.t, status=new_state.status,
            evento="Não pagou (parcela virou vencida)",
            paid=False, on_time=False, delay_days=0,
            parcela=parcela, juros=j, amort=0.0,
            extra=0.0, late=0.0, cash_out=0.0,
            principal_end=st.principal, overdue_end=new_overdue
        )
        if status == "default":
            row["evento"] = "Entrou em DEFAULT (faltas consecutivas atingiram o limite)"
        return new_state, row

def simulate(cfg: Config, decide: Callable[[Config, State, float], Decision]) -> Tuple[List[Dict], float]:
    parcela = price_payment(cfg.principal, cfg.rate, cfg.periods)
    st = State(1, cfg.principal, 0.0, "active", 0)
    rows: List[Dict] = []
    while st.t <= cfg.periods and st.status == "active":
        dc = decide(cfg, st, parcela)
        dc = Decision(bool(dc.will_pay), max(0, int(dc.delay_days)), max(0.0, float(dc.extra)))
        st, row = step(cfg, st, dc, parcela)
        rows.append(row)
    return rows, parcela

def resumo(rows: List[Dict], parcela_price: float) -> Dict:
    if not rows: return {}
    total_pago = sum(r.get("cash_out", 0.0) for r in rows)
    juros = sum(r.get("juros", 0.0) for r in rows)
    atraso = sum(r.get("late", 0.0) for r in rows)
    ontime = sum(1 for r in rows if r.get("on_time"))
    pagas = sum(1 for r in rows if r.get("paid"))
    status_final = rows[-1]["status"]
    return dict(
        parcela_price=parcela_price,
        total_pago=total_pago,
        juros=juros,
        encargos_atraso=atraso,
        parcelas_pagas=pagas,
        em_dia=ontime,
        status_final=status_final
    )

def moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_float(msg: str, minimo: Optional[float]=None) -> float:
    while True:
        s = input(msg).strip().replace(",", ".")
        try:
            v = float(s)
            if minimo is not None and v < minimo:
                print(f"• O valor deve ser ≥ {minimo}.")
                continue
            return v
        except ValueError:
            print("• Entrada inválida. Digite um número (aceita vírgula ou ponto).")

def parse_int(msg: str, minimo: Optional[int]=None, maximo: Optional[int]=None) -> int:
    while True:
        s = input(msg).strip()
        try:
            v = int(s)
            if minimo is not None and v < minimo:
                print(f"• O valor deve ser ≥ {minimo}.")
                continue
            if maximo is not None and v > maximo:
                print(f"• O valor deve ser ≤ {maximo}.")
                continue
            return v
        except ValueError:
            print("• Entrada inválida. Digite um número inteiro.")

def pause():
    input("\n(Pressione ENTER para continuar) ")

def poli_sempre_em_dia(cfg: Config, st: State, parcela: float) -> Decision:
    return Decision(True, 0, 0.0)

def mk_poli_atraso_fixo(dias: int) -> Callable[[Config, State, float], Decision]:
    def _p(cfg: Config, st: State, parcela: float) -> Decision:
        return Decision(True, dias, 0.0)
    return _p

def mk_poli_pula_mes(mes_que_pula: int) -> Callable[[Config, State, float], Decision]:
    def _p(cfg: Config, st: State, parcela: float) -> Decision:
        if st.t == mes_que_pula:
            return Decision(False, 0, 0.0)
        return Decision(True, 0, 0.0)
    return _p

def mk_poli_extra_fixo(extra: float) -> Callable[[Config, State, float], Decision]:
    def _p(cfg: Config, st: State, parcela: float) -> Decision:
        return Decision(True, 0, min(extra, st.principal))
    return _p

def mk_poli_sequencia(seq_tokens: List[str], atraso_padrao: int, extra_padrao: float) -> Callable[[Config, State, float], Decision]:
    seq = [t.strip().upper() for t in seq_tokens if t.strip()] or ["P"]
    def token_to_decision(tok: str, principal: float) -> Decision:
        if tok == "P": return Decision(True, 0, min(extra_padrao, principal))
        if tok == "A": return Decision(True, atraso_padrao, min(extra_padrao, principal))
        return Decision(False, 0, 0.0)
    def _p(cfg: Config, st: State, parcela: float) -> Decision:
        idx = min(st.t-1, len(seq)-1)
        return token_to_decision(seq[idx], st.principal)
    return _p

def explicar_termos():
    print("\nGuia rápido dos termos mostrados:")
    print("• Parcela (PRICE): valor fixo calculado para quitar o empréstimo em N parcelas.")
    print("• Juros do período: juros do mês sobre o saldo devedor.")
    print("• Amortização: parte da parcela que reduz o saldo devedor.")
    print("• Encargos de atraso: multa + mora se a parcela do mês atrasou.")
    print("• Amortização extra: valor adicional (opcional) para reduzir o saldo mais rápido.")
    print("• Vencido acumulado: parcelas não pagas de meses anteriores + mora sobre elas.\n")

def print_linha_resumida(r: Dict, t: int, n: int):
    status_txt = r['evento']
    print(f"Período {t}/{n} — {status_txt} — Saída de caixa: {moeda(r.get('cash_out',0.0))}")

def print_linha_detalhada(r: Dict, t: int, n: int):
    print(f"\nPeríodo {t}/{n} — {r['evento']}")
    print(f"  • Parcela do mês........: {moeda(r.get('parcela',0.0))}")
    print(f"  • Juros do período......: {moeda(r.get('juros',0.0))}")
    print(f"  • Amortização...........: {moeda(r.get('amort',0.0))}")
    print(f"  • Encargos de atraso....: {moeda(r.get('late',0.0))}")
    print(f"  • Amortização extra.....: {moeda(r.get('extra',0.0))}")
    print(f"  • Saída de caixa total..: {moeda(r.get('cash_out',0.0))}")
    print(f"  • Saldo devedor (fim)...: {moeda(r.get('principal_end',0.0))}")
    print(f"  • Vencido acumulado.....: {moeda(r.get('overdue_end',0.0))}")
    if r['status'] == "default":
        print("O contrato entrou em DEFAULT (atingiu o nº de faltas seguidas).")
    if r['status'] == "paid":
        print("Contrato quitado.")

def imprimir_resumo_final(m: Dict):
    print("\n=== Resumo Final ===")
    print(f"Parcela (PRICE).........: {moeda(m['parcela_price'])}")
    print(f"Status final............: {m['status_final']}")
    print(f"Total pago..............: {moeda(m['total_pago'])}")
    print(f"Juros somados...........: {moeda(m['juros'])}")
    print(f"Encargos de atraso......: {moeda(m['encargos_atraso'])}")
    print(f"Parcelas pagas..........: {m['parcelas_pagas']}  |  Em dia: {m['em_dia']}")

def configurar_contrato() -> Config:
    print("\n=== 1) Configurar Contrato de Microcrédito ===")
    pv = parse_float("1. Valor financiado (ex.: 2000): R$ ", minimo=0.01)
    n  = parse_int("2. Número de parcelas (ex.: 8): ", minimo=1)
    i  = parse_float("3. Juros ao mês (ex.: 0,028 = 2,8%): ", minimo=0.0)
    multa = parse_float("4. Multa por atraso (ex.: 0,02 = 2%): ", minimo=0.0)
    mora  = parse_float("5. Mora diária (ex.: 0,00033 ≈ 1% a.m.): ", minimo=0.0)
    df_missed = parse_int("6. Default após quantas faltas seguidas? (ex.: 2): ", minimo=1)
    dias = parse_int("7. Dias por período (30 padrão): ", minimo=1)
    cfg = Config(pv, n, i, multa, mora, df_missed, dias)
    print("\nContrato configurado!")
    return cfg

def escolher_politica(cfg: Config) -> Callable[[Config, State, float], Decision]:
    while True:
        print("\n=== 2) Escolher Política de Pagamento ===")
        print("1) Sempre em dia (paga todo mês, sem atraso)")
        print("2) Sempre com atraso fixo (defina os dias de atraso)")
        print("3) Pular uma parcela específica (não paga naquele mês)")
        print("4) Amortização extra fixa todo mês (acelera a quitação)")
        print("5) Sequência personalizada (ex.: P A N P) + atraso/extra padrão")
        op = input("Opção (1-5): ").strip()

        if op == "1":
            return poli_sempre_em_dia

        elif op == "2":
            dias = parse_int("Dias de atraso em todo mês (ex.: 7): ", minimo=0)
            return mk_poli_atraso_fixo(dias)

        elif op == "3":
            mes = parse_int(f"Qual nº da parcela será pulada? (1..{cfg.periods}): ", minimo=1, maximo=cfg.periods)
            return mk_poli_pula_mes(mes)

        elif op == "4":
            extra = parse_float("Valor de amortização extra por mês (ex.: 200): R$ ", minimo=0.0)
            return mk_poli_extra_fixo(extra)

        elif op == "5":
            print("\nUse P = paga em dia | A = paga com atraso | N = não paga")
            print("Exemplo: P A N P   (se acabar, repete o último token)")
            seq_str = input("Sequência: ").strip()
            tokens = seq_str.split()
            atraso = parse_int("Atraso padrão para 'A' (dias, ex.: 7): ", minimo=0)
            extra = parse_float("Extra padrão quando paga (ex.: 0 para nenhum): R$ ", minimo=0.0)
            return mk_poli_sequencia(tokens, atraso, extra)

        else:
            print("Opção inválida. Tente novamente.")

def executar_simulacao(cfg: Config, politica) -> None:
    print("\n=== 3) Simular ===")
    modo = input("Relatório [R]esumido ou [D]etalhado? (R/D): ").strip().upper() or "R"
    mostrar_guia = input("Mostrar explicação dos termos? (S/N): ").strip().upper() or "N"
    if mostrar_guia == "S":
        explicar_termos()

    rows, parcela = simulate(cfg, politica)
    if not rows:
        print("Nada a mostrar (verifique a configuração).")
        return

    n = cfg.periods
    for r in rows:
        t = r["period"]
        if modo == "D":
            print_linha_detalhada(r, t, n)
        else:
            print_linha_resumida(r, t, n)

    m = resumo(rows, parcela)
    imprimir_resumo_final(m)

def main():
    print("==============================================")
    print("          Simulador de Microcrédito           ")
    print("==============================================")
    cfg = None
    politica = None

    while True:
        print("\n=== Menu Principal ===")
        print("1) Configurar contrato")
        print("2) Escolher política de pagamento")
        print("3) Simular (resumo ou detalhado)")
        print("4) Explicar termos (o que cada campo significa)")
        print("5) Sair")
        op = input("Opção (1-5): ").strip()

        if op == "1":
            cfg = configurar_contrato()
            pause()

        elif op == "2":
            if not cfg:
                print("Configure o contrato primeiro (opção 1).")
            else:
                politica = escolher_politica(cfg)
                print("Política definida!")
            pause()

        elif op == "3":
            if not cfg:
                print("Configure o contrato primeiro (opção 1).")
            elif not politica:
                print("Escolha a política (opção 2).")
            else:
                executar_simulacao(cfg, politica)
            pause()

        elif op == "4":
            explicar_termos()
            pause()

        elif op == "5":
            print("Encerrando...")
            break

        else:
            print("Opção inválida, (1-5)")

if __name__ == "__main__":
    main()