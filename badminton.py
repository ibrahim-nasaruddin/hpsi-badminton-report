import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from fpdf import FPDF
from datetime import datetime
import tempfile
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HPSI- Badminton PDF Report", layout="wide")

# --- PDF CLASS DEFINITION ---
class BadmintonReport(FPDF):
    def __init__(self, custom_title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_title = custom_title

    def header(self):
        if self.page_no() == 1:
            self.set_fill_color(44, 62, 80)
            self.rect(0, 0, 210, 40, 'F')
            self.set_text_color(255, 255, 255)
            # Reduced font size from 20 to 14 to fit the longer dynamic text
            self.set_font("Arial", 'B', 14) 
            self.cell(0, 20, self.custom_title, ln=True, align='C')
            self.set_font("Arial", size=10)
            self.cell(0, 5, f"Prepared on: {datetime.now().strftime('%d-%m-%Y')}", ln=True, align='C')
            self.ln(20)

    def section_title(self, title):
        self.set_font("Arial", 'B', 14)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, title.upper(), ln=True)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def quick_table(self, header, data, col_widths):
        self.set_font("Arial", 'B', 9)
        self.set_fill_color(230, 230, 230)
        for i, h in enumerate(header):
            self.cell(col_widths[i], 7, h, border=1, fill=True, align='C')
        self.ln()
        self.set_font("Arial", size=9)
        self.set_text_color(0, 0, 0)
        for row in data:
            for i, item in enumerate(row):
                self.cell(col_widths[i], 7, str(item), border=1, align='C')
            self.ln()
        self.ln(5)

# --- ANALYTICS ENGINE ---
def analyze_match(df, p_name, o_name):
    df['Name'] = df['Name'].str.replace(r" \(\d+\)", "", regex=True)
    relevant = ["Player Serve", "Opponent Serve", "End Rally"]
    df = df[df['Name'].isin(relevant)].sort_values('Position').reset_index(drop=True)
    
    rallies = []
    current_p_score = 0
    current_o_score = 0
    current_set_label = ""

    for i in range(len(df)):
        name_i = df.iloc[i]['Name']
        set_i = df.iloc[i]['Period']

        if set_i != current_set_label:
            current_p_score, current_o_score = 0, 0
            current_set_label = set_i

        if "Serve" not in name_i:
            continue

        next_events = df.iloc[i+1:]
        end_rally_search = next_events[next_events['Name'] == "End Rally"]
        
        if not end_rally_search.empty:
            end_row_idx = end_rally_search.index[0]
            end_row = df.loc[end_row_idx]
            
            duration = (end_row['Position'] + 2000 - df.iloc[i]['Position']) / 1000
            server_side = "Player" if "Player" in name_i else "Opponent"
            
            winner = None
            after_end = df.iloc[end_row_idx+1:]
            next_serve_search = after_end[after_end['Name'].str.contains("Serve", na=False)]
            
            # WINNER INFERENCE LOGIC
            if not next_serve_search.empty:
                next_serve_name = next_serve_search.iloc[0]['Name']
                next_server_side = "Player" if "Player" in next_serve_name else "Opponent"
                
                if server_side == next_server_side:
                    winner = server_side
                else:
                    winner = "Opponent" if server_side == "Player" else "Player"
            else:
                # THE FIX: If it's the absolute final rally of the match (no next serve), 
                # the winner is the player who is currently leading / on match point.
                if current_p_score > current_o_score:
                    winner = "Player"
                elif current_o_score > current_p_score:
                    winner = "Opponent"
                else:
                    winner = server_side 

            score_diff = abs(current_p_score - current_o_score)
            is_pressure = (score_diff <= 1) or (current_p_score >= 20) or (current_o_score >= 20)

            rallies.append({
                "Set": current_set_label,
                "Rally_Num": len([r for r in rallies if r['Set'] == current_set_label]) + 1,
                "Server": server_side,
                "Winner": winner,
                "Duration": duration,
                "Start_Pos": df.iloc[i]['Position'],
                "End_Pos": end_row['Position'] + 2000,
                "Cat": "Short" if duration < 7 else ("Mid" if duration <= 15 else "Long"),
                "Is_Pressure": is_pressure,
                "P_Score_Before": current_p_score,
                "O_Score_Before": current_o_score
            })
            
            if winner == "Player": current_p_score += 1
            else: current_o_score += 1
    
    rdf = pd.DataFrame(rallies)
    rdf['Rest'] = (rdf.groupby('Set')['Start_Pos'].shift(-1) - rdf['End_Pos']) / 1000
    rdf['Ratio'] = rdf['Rest'] / rdf['Duration'] 
    
    return rdf

# --- MAIN INTERFACE ---
st.title("🏸 HPSI Badminton Analytics- PDF Report Generation")

with st.sidebar:
    st.header("Match Metadata")
    event = st.text_input("Event", "YONEX German Open 2026")
    date_str = st.date_input("Date", datetime(2026, 2, 26))
    venue = st.text_input("Venue", "Germany")
    round_m = st.text_input("Round", "R16")
    p_name = st.text_input("Player Name", "YEO Jia Min")
    o_name = st.text_input("Opponent Name", "HAN Qian Xi")

uploaded_file = st.file_uploader("Upload DartFish CSV", type="csv")

if uploaded_file:
    raw_df = pd.read_csv(uploaded_file)
    rdf = analyze_match(raw_df, p_name, o_name)
    
    if st.button("Generate Full PDF Report"):
        # Combine the variables into the dynamic title string
        date_formatted = date_str.strftime("%d %b %Y")
        dynamic_title = f"{date_formatted} | {event} | {round_m} | {p_name} vs {o_name}"
        
        # Pass the custom title into the newly updated class
        pdf = BadmintonReport(custom_title=dynamic_title)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # --- 1. EVENT SUMMARY ---
        pdf.section_title("Event Summary")
        if not rdf.empty:
            total_duration_seconds = (rdf['End_Pos'].max() - rdf['Start_Pos'].min()) / 1000
            duration_str = f"{int(total_duration_seconds // 60)} min {int(total_duration_seconds % 60)} sec"
        else:
            duration_str = "0 min 0 sec"

        set_stats = rdf.groupby('Set').agg({'P_Score_Before': 'max', 'O_Score_Before': 'max', 'Winner': 'last'})
        final_scores = []
        for idx, row in set_stats.iterrows():
            p_final = int(row['P_Score_Before'] + (1 if row['Winner'] == 'Player' else 0))
            o_final = int(row['O_Score_Before'] + (1 if row['Winner'] == 'Opponent' else 0))
            final_scores.append(f"{p_final}-{o_final}")
        
        p_sets = sum(1 for s in final_scores if int(s.split('-')[0]) > int(s.split('-')[1]))
        match_winner = p_name if p_sets > (len(final_scores)/2) else o_name
        match_vs = f"{p_name} vs {o_name}"

        summary_table = [
            ["Date", str(date_str)], ["Event", event], ["Round", round_m], ["Match", match_vs], 
            ["Venue", venue], ["Winner", match_winner], ["Final Score", ", ".join(final_scores)],
            ["Duration", duration_str]
        ]
        pdf.quick_table(["Variable", "Value"], summary_table, [50, 100])

        # --- 2. OVERALL MATCH SUMMARY ---
        pdf.section_title("Overall Match Summary")
        avg_rally = rdf['Duration'].mean()
        valid_rest = rdf[rdf['Rest'] > 0.1]['Rest']
        avg_rest = valid_rest.mean()
        dist = rdf['Cat'].value_counts(normalize=True) * 100
        overall_table = [
            ["Total Points Played", len(rdf)],
            ["Avg Rally Duration (s)", f"{avg_rally:.1f}"],
            ["Avg Rest Duration (s)", f"{avg_rest:.1f}"],
            ["Work:Rest Ratio", f"1 : {avg_rest/avg_rally:.1f}"],
            ["Short/Mid/Long %", f"{dist.get('Short',0):.0f}% / {dist.get('Mid',0):.0f}% / {dist.get('Long',0):.0f}%"]
        ]
        pdf.quick_table(["Metric", "Value"], overall_table, [80, 60])

        # --- 3. PLAYER MATCH SUMMARY ---
        pdf.add_page()
        pdf.section_title("Player Match Summary")
        
        def get_p_stats(side):
            win_sub = rdf[rdf['Winner'] == side]
            serve_sub = rdf[rdf['Server'] == side]
            pres_sub = rdf[rdf['Is_Pressure'] == True]
            p_wins = len(win_sub)
            p_rally = win_sub['Duration'].mean() if not win_sub.empty else 0.0
            p_rest = win_sub['Rest'].mean() if not win_sub.empty else 0.0
            s_wins = len(serve_sub[serve_sub['Winner'] == side])
            s_display = f"{(s_wins/len(serve_sub)*100):.0f}% ({s_wins})" if len(serve_sub)>0 else "0% (0)"
            pr_wins = len(pres_sub[pres_sub['Winner'] == side])
            pr_display = f"{(pr_wins/len(pres_sub)*100):.0f}% ({pr_wins})" if len(pres_sub)>0 else "0% (0)"
            dist_str = "0% / 0% / 0%"
            if not win_sub.empty:
                d = win_sub['Cat'].value_counts(normalize=True) * 100
                dist_str = f"{d.get('Short',0):.0f}% / {d.get('Mid',0):.0f}% / {d.get('Long',0):.0f}%"
            return p_wins, p_rally, p_rest, s_display, pr_display, dist_str

        p_v = get_p_stats("Player")
        o_v = get_p_stats("Opponent")
        
        player_table = [
            ["Total Points Won %", f"{p_v[0]/len(rdf)*100:.1f}% ({p_v[0]})", f"{o_v[0]/len(rdf)*100:.1f}% ({o_v[0]})"],
            ["Avg Rally Duration (s)", f"{p_v[1]:.1f}", f"{o_v[1]:.1f}"],
            ["Avg Rest Duration (s)", f"{p_v[2]:.1f}", f"{o_v[2]:.1f}"],
            ["Work:Rest Ratio", f"1 : {p_v[2]/p_v[1]:.1f}" if p_v[1] > 0 else "N/A", f"1 : {o_v[2]/o_v[1]:.1f}" if o_v[1] > 0 else "N/A"],
            ["Serve Win %", p_v[3], o_v[3]],
            ["Pressure Points Won %", p_v[4], o_v[4]],
            ["Short/Mid/Long (%) distribution", p_v[5], o_v[5]]
        ]
        pdf.quick_table(["Metric", p_name, o_name], player_table, [70, 60, 60])

        # --- 4. SERVE STATISTICS SUMMARY ---
        pdf.add_page()
        pdf.section_title("Serve Statistics Summary")
        
        def get_serve_summary_text(side_label, side_name):
            subset = rdf[rdf['Server'] == side_label]
            total = len(subset)
            if total == 0: return f"{side_name} Serves: 0"
            p_wins = len(subset[subset['Winner'] == 'Player'])
            o_wins = len(subset[subset['Winner'] == 'Opponent'])
            p_pct = (p_wins / total) * 100
            o_pct = (o_wins / total) * 100
            
            # REPLACED '•' with '-' to fix the FPDF Unicode Encoding Error
            return (f"{side_name} Serves: {total}\n"
                    f"- {p_pct:.0f}% ({p_wins}) won by {p_name}\n"
                    f"- {o_pct:.0f}% ({o_wins}) won by {o_name}")

        pdf.set_font("Arial", 'B', 10)
        pdf.set_x(10) 
        pdf.multi_cell(190, 6, get_serve_summary_text("Player", p_name))
        pdf.ln(3)
        pdf.set_x(10)
        pdf.multi_cell(190, 6, get_serve_summary_text("Opponent", o_name))
        pdf.ln(5)

        # Serve Outcome Breakdown Plot
        fig_serve, ax_serve = plt.subplots(figsize=(8, 5))
        
        # Group data to get counts and percentages
        serve_counts = rdf.groupby(['Server', 'Winner']).size().reset_index(name='counts')
        serve_totals = rdf.groupby('Server').size().reset_index(name='totals')
        serve_plot_data = serve_counts.merge(serve_totals, on='Server')
        serve_plot_data['pct'] = (serve_plot_data['counts'] / serve_plot_data['totals']) * 100

        # MAPPING UPDATE: Map both Server AND Winner to the actual player names
        serve_plot_data['Server'] = serve_plot_data['Server'].map({'Player': p_name, 'Opponent': o_name})
        serve_plot_data['Winner'] = serve_plot_data['Winner'].map({'Player': p_name, 'Opponent': o_name})
        serve_totals['Server'] = serve_totals['Server'].map({'Player': p_name, 'Opponent': o_name})
        
        # Explicitly define the order to render the bars
        server_order = [p_name, o_name]
        
        # STRICT COLOR MAPPING: Lock specific names to specific hex codes
        color_map = {p_name: '#FFA600', o_name: '#2C3E50'}

        sns.barplot(
            data=serve_plot_data, 
            x='Server', 
            y='pct', 
            hue='Winner', 
            hue_order=[o_name, p_name], # Sets the order they appear in the legend
            order=server_order,
            ax=ax_serve, 
            palette=color_map # Applies the strict color map dictionary
        )
        
        # Add Data Labels: 70% (20)
        for p in ax_serve.patches:
            height = p.get_height()
            if height > 0:
                # Use the x-coordinate of the bar to find which Server index it belongs to
                idx = int(round(p.get_x() + p.get_width() / 2.0))
                
                # Safety check to prevent index errors
                if 0 <= idx < len(server_order):
                    server_name = server_order[idx]
                    
                    # Retrieve the absolute total for this specific server
                    total = serve_totals[serve_totals['Server'] == server_name]['totals'].values[0]
                    count = int(round((height / 100) * total))
                    
                    ax_serve.text(p.get_x() + p.get_width()/2., height / 2,
                                f'{height:.0f}% ({count})', 
                                ha='center', va='center', color='white', fontweight='bold', fontsize=9)

        ax_serve.set_title("Serve Outcome Breakdown", fontsize=14)
        ax_serve.set_xlabel("")  
        ax_serve.set_ylabel("Percentage of Points Won (%)")
        ax_serve.set_ylim(0, 110)
        
        # Removed the manual 'labels' override so Seaborn reads the names naturally from the DataFrame
        ax_serve.legend(title="Won By:", loc='upper right')
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            plt.savefig(tmp.name, bbox_inches='tight', dpi=150)
            pdf.image(tmp.name, x=30, w=150)
            os.remove(tmp.name)
        plt.close()

        # --- 4.1 RALLY STATISTICS SUMMARY ---
        pdf.add_page()
        pdf.section_title("Rally Statistics Summary")
        
        pdf.set_font("Arial", 'I', 10)
        pdf.set_x(10)
        pdf.cell(190, 10, "Rally Categories: Short (<7s), Mid (7-15s), Long (>15s)", ln=True)
        pdf.ln(5)

        # Plot 1: Rally Length Distribution
        fig_dist, ax_dist = plt.subplots(figsize=(8, 4))
        rdf['Cat'] = pd.Categorical(rdf['Cat'], categories=['Short', 'Mid', 'Long'], ordered=True)
        cat_counts = rdf['Cat'].value_counts(sort=False)
        cat_pcts = (cat_counts / len(rdf)) * 100
        
        bars = ax_dist.bar(cat_counts.index.astype(str), cat_pcts, color='#2C3E50', width=0.6)
        ax_dist.set_title("Rally Length Distribution", fontweight='bold')
        ax_dist.set_ylabel("Percentage of Rallies (%)")
        ax_dist.set_ylim(0, max(cat_pcts) + 15)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            count = cat_counts.iloc[i]
            ax_dist.text(bar.get_x() + bar.get_width()/2., height + 1,
                        f'{height:.0f}% ({count})', ha='center', va='bottom', fontweight='bold')

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            plt.savefig(tmp.name, bbox_inches='tight', dpi=150)
            pdf.image(tmp.name, x=30, w=150)
            os.remove(tmp.name)
        plt.close()
        pdf.ln(10)

        # Plot 2: Win % by Rally Category
        fig_win_cat, ax_win_cat = plt.subplots(figsize=(8, 5))
        
        # Group to get percentages and absolute counts
        win_cat_counts = rdf.groupby(['Cat', 'Winner']).size().unstack(fill_value=0)
        
        # Safety check: Ensure both columns exist even if a player scored 0 in a category
        for col in ['Opponent', 'Player']:
            if col not in win_cat_counts.columns:
                win_cat_counts[col] = 0
                
        # STRICT COLOR MAPPING: Force Opponent first (Navy: #2C3E50), Player second (Gold: #FFA600)
        win_cat_counts = win_cat_counts[['Opponent', 'Player']]
        
        win_cat_totals = win_cat_counts.sum(axis=1)
        win_cat_props = win_cat_counts.div(win_cat_totals, axis=0).mul(100)
        win_cat_props = win_cat_props.reindex(['Short', 'Mid', 'Long'])
        
        # Rename the columns to actual player names for the legend
        win_cat_props.columns = [o_name, p_name]
        win_cat_counts.columns = [o_name, p_name]
        
        ax_p = win_cat_props.plot(
            kind='bar', 
            stacked=True, 
            ax=ax_win_cat, 
            color=['#2C3E50', '#FFA600'] 
        )
        
        # Add Data Labels to Stacked Bars: 70% (20)
        for i, (idx, row) in enumerate(win_cat_props.iterrows()):
            cumulative_height = 0
            for winner in win_cat_props.columns:
                val = row[winner]
                if val > 0:
                    count = int(win_cat_counts.loc[idx, winner])
                    label = f"{val:.0f}% ({count})"
                    ax_win_cat.text(i, cumulative_height + (val / 2), label, 
                                   ha='center', va='center', color='white', fontweight='bold', fontsize=8)
                cumulative_height += val

        ax_win_cat.set_title("Win % by Rally Category", fontweight='bold')
        ax_win_cat.set_ylabel("Win Percentage (%)")
        
        # THE FIX: Explicitly set the x-axis label to overwrite "Cat"
        ax_win_cat.set_xlabel("Rally Category") 
        
        ax_win_cat.legend(title="Won By:", loc='upper right')
        plt.xticks(rotation=0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            plt.savefig(tmp.name, bbox_inches='tight', dpi=150)
            pdf.image(tmp.name, x=30, w=150)
            os.remove(tmp.name)
        plt.close()

        # --- 5. POINT PROGRESSION & LOAD PER SET ---
        # We start the section title on its own page
        pdf.add_page()
        pdf.section_title("Point Progression & Load per Set")
        
        col_work, col_player, col_opponent = "#F5EDC8", "#FFA600", "#2C3E50"

        # Helper function to format seconds into MM:SS for the X-axis
        def format_mmss(seconds):
            m, s = divmod(int(max(0, seconds)), 60)
            return f"{m:02d}:{s:02d}"

        # Iterate through each unique set found in the processed data
        for s_name in rdf['Set'].unique():
            # Force a NEW PAGE for every set (Set 1, Set 2, Set 3 each get their own page)
            # We check if it's the very first set to avoid a blank page after the section title
            if s_name != rdf['Set'].unique()[0]:
                pdf.add_page()

            # Clean the set title (e.g., "1. Set" becomes "Set 1")
            clean_set_title = f"Set {int(''.join(filter(str.isdigit, str(s_name))))}"
            s_df = rdf[rdf['Set'] == s_name].copy().sort_values('Start_Pos')
            
            # --- A. LOAD STATISTICS TABLE ---
            # Filter criteria: exclude 0 rest and technical intervals > 45s
            stats_data = s_df[(s_df['Rest'] > 0.1) & (s_df['Rest'] < 45)].copy()
            
            if not stats_data.empty:
                load_rows = [
                    ["Work Duration (s)", f"{stats_data['Duration'].max():.1f}", f"{stats_data['Duration'].min():.1f}", f"{stats_data['Duration'].mean():.1f}"],
                    ["Rest Duration (s)", f"{stats_data['Rest'].max():.1f}", f"{stats_data['Rest'].min():.1f}", f"{stats_data['Rest'].mean():.1f}"],
                    # Logic: Max intensity is the Minimum ratio value (least rest per work)
                    ["Work:Rest Ratio (1:X)", f"1 : {stats_data['Ratio'].min():.1f}", f"1 : {stats_data['Ratio'].max():.1f}", f"1 : {stats_data['Ratio'].mean():.1f}"]
                ]
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 10, f"Load Statistics (Rest Intervals Excluded) - {clean_set_title}", ln=True)
                pdf.quick_table(["Metric", "Max (Intense)", "Min (Intense)", "Mean"], load_rows, [50, 35, 35, 30])
            
            # --- B. POINT PROGRESSION PLOT ---
            # Normalize timestamps so each set starts at 0:00
            set_start_ms = s_df['Start_Pos'].min()
            s_df['Start_Rel'] = (s_df['Start_Pos'] - set_start_ms) / 1000
            s_df['End_Rel'] = (s_df['End_Pos'] - set_start_ms) / 1000
            s_df['P_Cum'] = (s_df['Winner'] == 'Player').cumsum()
            s_df['O_Cum'] = (s_df['Winner'] == 'Opponent').cumsum()
            
            fig, ax = plt.subplots(figsize=(10, 5))
            
            # Shading for Work periods
            for _, rally in s_df.iterrows():
                ax.axvspan(rally['Start_Rel'], rally['End_Rel'], color=col_work, alpha=0.5)

            # Step plot for score progression
            x_steps = [0] + list(s_df['End_Rel'])
            p_steps = [0] + list(s_df['P_Cum'])
            o_steps = [0] + list(s_df['O_Cum'])
            ax.step(x_steps, p_steps, where='post', color=col_player, linewidth=2, label=p_name)
            ax.step(x_steps, o_steps, where='post', color=col_opponent, linewidth=2, label=o_name)
            
            # Numerical Score Labels
            for _, row in s_df.iterrows():
                x_pos = row['End_Rel']
                score_val = int(row['P_Score_Before']+1) if row['Winner']=='Player' else int(row['O_Score_Before']+1)
                color = col_player if row['Winner']=='Player' else col_opponent
                ax.text(x_pos, score_val + 0.6, str(score_val), color=color, fontsize=7, fontweight='bold', ha='center')

            import matplotlib.ticker as ticker
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{int(x//60):02d}:{int(x%60):02d}"))
            ax.set_title(f"Point Progression Timeline - {clean_set_title}", fontsize=12, fontweight='bold')
            ax.set_xlabel("Time in Set (mm:ss)")
            ax.set_ylabel("Points")
            ax.legend(loc='lower right', fontsize=9)
            ax.grid(axis='y', alpha=0.3)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                plt.savefig(tmp.name, bbox_inches='tight', dpi=150)
                pdf.image(tmp.name, x=10, w=190)
                os.remove(tmp.name)
            plt.close()
            pdf.ln(10)

        # --- 6. TOP 10 TOUGHEST RALLIES ---
        pdf.add_page()
        pdf.section_title("Top 10 Toughest Rallies (by Work:Rest Ratio)")
        set_totals = rdf.groupby('Set').size().to_dict()
        toughest_df = rdf[rdf['Ratio'].notna()].copy()
        
        top_10 = toughest_df.sort_values('Ratio', ascending=True).head(10).reset_index(drop=True)
        
        toughest_table_data = []
        for i, row in top_10.iterrows():
            set_label = f"Set {int(''.join(filter(str.isdigit, str(row['Set']))))}"
            rally_label = f"{int(row['Rally_Num'])}/{set_totals.get(row['Set'], 0)}"
            score_before = f"{int(row['P_Score_Before'])}-{int(row['O_Score_Before'])}"
            toughest_table_data.append([i+1, set_label, rally_label, f"{row['Ratio']:.2f}", f"{row['Duration']:.1f}", f"{row['Rest']:.1f}", score_before])
            
        pdf.quick_table(["No.", "Set #", "Rally #", "W:R Ratio", "Work (s)", "Rest (s)", "Score Before"], toughest_table_data, [10, 25, 25, 30, 25, 25, 50])
        pdf.set_font("Arial", 'I', 9)
        pdf.multi_cell(0, 5, "Note: A smaller W:R ratio represents a higher intensity rally (less rest per unit of work).")

        # --- 7. FINAL METHODOLOGY & NOTES ---
        pdf.add_page()
        pdf.section_title("NOTES: Methodology & Data Assumptions")
        pdf.set_font("Arial", size=10)
        
        methodology_text = (
            "Rally Construction: Rallies were reconstructed using the time stamp (Position) of the Serve and End Rally tags. "
            "A 2000ms (2-second) buffer was added to the End Rally time stamp to account for the shuttle being in play "
            "before the tag was registered.\n\n"
            "Winner Logic: The winner of each rally was inferred based on the service flow. If the server retained the "
            "service for the subsequent point, they were deemed the winner; if the service changed hands, the receiver "
            "was deemed the winner.\n\n"
            "Rest Time: Defined as the duration between the end of one rally (including the buffer) and the start of the "
            "next serve. Calculations exclude values of zero or technical intervals (>45s) to prevent skewed statistics.\n\n"
            "Pressure Points: Defined as rallies where the score difference was <=1 point, or where the score of either "
            "player exceeded 20 points."
        )
        pdf.multi_cell(0, 8, methodology_text)

        # --- FINALIZE & DYNAMIC NAMING ---
        # 1. Format Date as YYYYMMDD
        date_formatted = date_str.strftime("%Y%m%d")
        
        # 2. Calculate Match Score (Sets Won)
        # We look at the final scores of each set to see who won more sets
        p_sets_won = 0
        o_sets_won = 0
        for s in final_scores:
            p_final = int(s.split('-')[0])
            o_final = int(s.split('-')[1])
            if p_final > o_final:
                p_sets_won += 1
            else:
                o_sets_won += 1
        
        match_score_str = f"{p_sets_won}-{o_sets_won}"
        
        # 3. Construct Filename
        # Convention: YYYYMMDD Competition Round Player MatchScore Opponent
        clean_event = event.replace(" ", "_") # Optional: replace spaces for URL safety
        filename = f"{date_formatted} {event} {round_m} {p_name} {match_score_str} {o_name}.pdf"
        
        # 4. Prepare Download
        pdf_output = pdf.output(dest='S')
        pdf_bytes = bytes(pdf_output)
        
        st.download_button(
            label="📥 Download Full PDF Match Report", 
            data=pdf_bytes, 
            file_name=filename,
            mime="application/pdf"
        )
else:
    st.info("Please upload your DartFish CSV.")
