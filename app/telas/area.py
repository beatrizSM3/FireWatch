"""Escolher uma área que não está na lista: Cerrado inteiro, desenho no mapa ou ponto + raio."""
from __future__ import annotations

import folium
import streamlit as st
from folium.plugins import Draw
from shapely.geometry import shape
from streamlit_folium import st_folium

import dados as D
import estado
import estilo as E
from componentes import SATELITE


def _usar_ponto() -> None:
    lat, lon, raio = (st.session_state[k] for k in ("pt_lat", "pt_lon", "pt_raio"))
    estado.ir(a=f"pt:{lat:.4f},{lon:.4f},{raio:g}", v="territorio")


@st.dialog("Desenhe a área", width="large")
def _desenhar() -> None:
    st.caption("Use o polígono ou o retângulo no canto do mapa.")
    m = folium.Map(location=[-13.5, -48.5], zoom_start=5, tiles=None, control_scale=True)
    folium.TileLayer(SATELITE, attr="Esri World Imagery", name="Satélite").add_to(m)
    Draw(export=False, draw_options=dict(polyline=False, circle=False, marker=False,
                                         circlemarker=False, polygon=True, rectangle=True),
         edit_options=dict(edit=False)).add_to(m)
    out = st_folium(m, height=460, width=None, returned_objects=["last_active_drawing"],
                    key="mapa_desenho")
    desenho = (out or {}).get("last_active_drawing")
    if not desenho:
        return
    geom = desenho.get("geometry", desenho)
    km2 = D._area_km2(shape(geom))
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    c1.markdown(f"**{E.num(km2)} km²**")
    if km2 > 400_000:
        c1.caption("Área muito grande: os cálculos podem demorar.")
    if c2.button("Usar esta área", type="primary", width="stretch"):
        estado.ir(a=D.guardar_desenho(geom), v="territorio")
        st.rerun()


def seletor_outra_area() -> None:
    with st.popover("Área", icon=":material/tune:", width="stretch",
                    help="Cerrado inteiro, desenho no mapa ou ponto + raio"):
        st.button("Cerrado inteiro", icon=":material/public:", width="stretch",
                  on_click=estado.ir, kwargs=dict(a="cerrado", v="territorio"))
        if st.button("Desenhar no mapa", icon=":material/draw:", width="stretch"):
            _desenhar()
        st.divider()
        c1, c2 = st.columns(2)
        c1.number_input("Latitude", value=-10.5, min_value=-34.0, max_value=6.0, step=0.1,
                        format="%.3f", key="pt_lat")
        c2.number_input("Longitude", value=-46.5, min_value=-74.0, max_value=-34.0, step=0.1,
                        format="%.3f", key="pt_lon")
        st.slider("Raio (km)", 5, 200, 30, step=5, key="pt_raio")
        st.button("Usar ponto + raio", icon=":material/my_location:", width="stretch",
                  on_click=_usar_ponto)
