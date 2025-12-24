import streamlit as st
import pandas as pd
from src.db_manager import DBManager

# Page Config
st.set_page_config(
    page_title="Gemini RSI Buy Advisor",
    page_icon="🤖",
    layout="wide"
)

def main():
    st.title("🤖 Gemini RSI Buy Advisor Results")
    st.markdown("Automated analysis of Low-RSI KOSDAQ stocks using Gemini & real-time news.")

    # Sidebar: Date Selection
    db = DBManager()
    available_dates = db.get_all_dates()
    
    if not available_dates:
        st.warning("No data found in database yet. Run the daily job first.")
        return

    selected_date = st.sidebar.selectbox("Select Date", available_dates, index=0)
    
    st.header(f"📅 Analysis for {selected_date}")
    
    # Fetch Data
    results = db.get_advice_by_date(selected_date)
    
    if not results:
        st.info("No advice records for this date.")
        return
    
    # Convert to DataFrame for summary stats
    df = pd.DataFrame(results)
    
    # Metrics
    total = len(df)
    yes_count = len(df[df['recommendation'] == 'YES'])
    no_count = len(df[df['recommendation'] == 'NO'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Candidates", total)
    col2.metric("Recommended (YES)", yes_count)
    col3.metric("Rejected (NO)", no_count)
    
    st.divider()
    
    # Detailed List with Expanders
    # Group by Recommendation
    yes_df = df[df['recommendation'] == 'YES']
    no_df = df[df['recommendation'] == 'NO']
    
    st.subheader("✅ Recommended to BUY")
    if yes_df.empty:
        st.write("No 'YES' recommendations.")
    else:
        for _, row in yes_df.iterrows():
            with st.expander(f"**{row['name']}** ({row['code']}) | RSI: {row['rsi']:.2f}"):
                st.write(f"**Decision:** {row['recommendation']}")
                st.info(row['reasoning'])
    
    st.subheader("❌ Recommended to HOLD/SKIP")
    if no_df.empty:
        st.write("No 'NO' recommendations.")
    else:
        for _, row in no_df.iterrows():
            with st.expander(f"**{row['name']}** ({row['code']}) | RSI: {row['rsi']:.2f}"):
                st.write(f"**Decision:** {row['recommendation']}")
                st.caption(row['reasoning'])

    if st.sidebar.button("Refresh Data"):
        st.rerun()

if __name__ == "__main__":
    main()
