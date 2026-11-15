"""Estado da navegação, guardado na URL (?v=…&a=…&m=…&c=…).

Guardar na URL permite compartilhar o link de um território/mês e recarregar a página sem
perder o lugar. Toda mudança de tela passa por `ir()`, usada como callback dos botões.

    v  tela: territorio | alerta | sensor | mif | entorno
    a  área (ver dados.Area): id do território, "cerrado", "pt:lat,lon,km" ou "geo:<hash>"
    m  mês em foco, "AAAA-MM"
    c  data de corte do Modo MIF, "MM-DD"
"""
from __future__ import annotations

import streamlit as st

TELAS = ("territorio", "alerta", "sensor", "mif", "entorno")


def ler() -> dict:
    q = st.query_params
    v = q.get("v", "territorio")
    return dict(v=v if v in TELAS else "territorio", a=q.get("a"), m=q.get("m"), c=q.get("c"))


def ir(**mudancas) -> None:
    """Atualiza a URL. Valor None remove o parâmetro."""
    for k, v in mudancas.items():
        if v is None:
            st.query_params.pop(k, None)
        else:
            st.query_params[k] = v


def ir_do_widget(chave_widget: str, param: str) -> None:
    """Callback de widget: copia o valor escolhido para a URL."""
    valor = st.session_state.get(chave_widget)
    if valor is not None:
        ir(**{param: valor})
