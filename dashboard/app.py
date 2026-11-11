"""Dashboard connecté à PostgreSQL (lit les vues consolidées).

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

from txpipeline.config import Settings

SERIES_COLOR = "#2a78d6"  # une seule série par graphique -> une seule teinte, pas de légende

st.set_page_config(page_title="Transactions — pipeline", layout="wide")


@st.cache_data(ttl=15)
def query(sql: str) -> pd.DataFrame:
    with psycopg.connect(Settings.from_env().database_url, connect_timeout=5) as conn:
        cur = conn.execute(sql)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def bar_chart(df: pd.DataFrame, label: str, value: str, title: str) -> alt.Chart:
    df = df.assign(**{value: df[value].astype(float)})
    return (
        alt.Chart(df, title=title)
        .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4, size=18)
        .encode(
            x=alt.X(f"{value}:Q", title="Montant (€)", axis=alt.Axis(grid=True, format=",.0f")),
            y=alt.Y(f"{label}:N", sort="-x", title=None),
            tooltip=[alt.Tooltip(f"{label}:N", title=label),
                     alt.Tooltip(f"{value}:Q", title="Montant (€)", format=",.2f")],
        )
        .properties(height=alt.Step(28))
        .configure_axis(gridOpacity=0.3, domain=False)
    )


st.title("Transactions financières")
st.caption("Données issues de la pipeline CSV → S3 → traitement → PostgreSQL. "
           "Rafraîchissement automatique toutes les 15 s.")

try:
    kpi = query("""SELECT (SELECT COUNT(*) FROM processed_files) AS files,
                          COUNT(*) AS n, COALESCE(SUM(montant), 0) AS total,
                          COUNT(*) FILTER (WHERE is_flagged) AS flagged
                   FROM transactions""").iloc[0]
except psycopg.Error as exc:
    st.error(f"Base inaccessible ou schéma absent : {exc}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fichiers traités", int(kpi.files))
c2.metric("Transactions", int(kpi.n))
c3.metric("Montant total", f"{float(kpi.total):,.2f} €".replace(",", " "))
c4.metric("Transactions flaggées (> 5 000 €)", int(kpi.flagged))

if int(kpi.n) == 0:
    st.info("Aucune donnée pour l'instant : déposez des CSV dans le S3 (préfixe incoming/).")
    st.stop()

left, right = st.columns(2)
with left:
    st.altair_chart(bar_chart(query("SELECT iban, total_sent FROM v_sent_by_iban"),
                              "iban", "total_sent", "Montants envoyés par IBAN"),
                    width="stretch")
    st.altair_chart(bar_chart(query("SELECT bank AS banque, total_sent FROM v_sent_by_bank"),
                              "banque", "total_sent", "Montants envoyés par banque"),
                    width="stretch")
with right:
    st.altair_chart(bar_chart(query("SELECT iban, total_received FROM v_received_by_iban"),
                              "iban", "total_received", "Montants reçus par IBAN"),
                    width="stretch")

st.subheader("⚠ Transactions flaggées (montant > 5 000 €)")
st.dataframe(
    query("""SELECT transaction_id, datetime_transaction, iban_origine, banque_source,
                    iban_destinataire, montant, file_name
             FROM v_flagged_transactions ORDER BY datetime_transaction"""),
    hide_index=True, width="stretch",
)

with st.expander("Fichiers traités (registre anti-doublon)"):
    st.dataframe(query("SELECT id, file_name, file_hash, row_count, processed_at "
                       "FROM processed_files ORDER BY id"),
                 hide_index=True, width="stretch")
