#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def parse_thresholds(thr_str, default_list):
    if thr_str:
        return [float(x) for x in thr_str.split(',')]
    return default_list


def find_cluster_file(cluster_dir: Path, sim: float):
    fmt_vals = [f"{sim:.2f}", f"{sim:.1f}", f"{sim:.0f}"]
    candidates = []
    for v in fmt_vals:
        candidates.append(cluster_dir / f"merged_sim_{v}.csv")
        candidates.append(cluster_dir / f"collapsed_sim_{v}.csv")
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"Missing cluster file for similarity {sim:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Average edges per representative over thresholds")
    ap.add_argument('--cluster-dir', required=True, help='Dir with merged_sim_*.csv or collapsed_sim_*.csv')
    ap.add_argument('--thresholds', default=None, help='Comma list of distance thresholds (e.g., 0.6,0.5,0.4)')
    ap.add_argument('--distance-mode', action='store_true', help='Interpret thresholds as cosine distance (default)')
    ap.add_argument('--out', default='avg_edges_per_rep.csv', help='Output CSV path')
    ap.add_argument('--plotly', action='store_true', help='Also render a Plotly chart (NASA/JPL vibe)')
    ap.add_argument('--plotly-static', action='store_true',
                    help='Save Plotly chart as static PNG via kaleido (no browser needed)')
    ap.add_argument('--seaborn', action='store_true', help='Also render a Seaborn PNG (aqua-on-charcoal theme)')
    ap.add_argument('--bokeh', action='store_true', help='Also render a Bokeh HTML (interactive, no browser needed)')
    args = ap.parse_args()

    default_dist_list = [0.60, 0.50, 0.40, 0.30, 0.20, 0.10]
    thresholds = parse_thresholds(args.thresholds, default_dist_list)
    if not args.distance_mode:
        # If user wants similarity mode, leave as-is; else convert distances to similarity for lookup
        pass

    cluster_dir = Path(args.cluster_dir)

    rows = []
    for thr in thresholds:
        if args.distance_mode or args.thresholds is None:
            sim = 1.0 - thr
            label_val = thr  # report distance
            label_type = 'distance'
        else:
            sim = thr
            label_val = thr
            label_type = 'similarity'
        fpath = find_cluster_file(cluster_dir, sim)
        df = pd.read_csv(fpath)
        if 'total_count' not in df.columns:
            raise SystemExit(f"File {fpath} missing total_count column")
        avg_edges = df['total_count'].mean()
        rows.append({
            'threshold_type': label_type,
            'threshold': label_val,
            'similarity_used': sim,
            'file': fpath.name,
            'representatives': len(df),
            'avg_edges_per_new_edge_name': avg_edges
        })

    out_path = Path(args.out)
    df_out = pd.DataFrame(rows)
    df_out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} with {len(rows)} rows")

    # Seaborn static plot
    if args.seaborn:
        try:
            import seaborn as sns
            import matplotlib.pyplot as plt
            # NASA/JPL / The Martian vibe: deep space charcoal with warm Mars accents
            sns.set_theme(style="whitegrid", rc={
                "axes.facecolor": "#0b0f16",
                "figure.facecolor": "#0b0f16",
                "grid.color": "#1f2735",
                "axes.edgecolor": "#324155",
                "text.color": "#f1f5f9",
                "axes.labelcolor": "#e2e8f0",
                "xtick.color": "#cbd5e1",
                "ytick.color": "#cbd5e1",
                # bundled mono to avoid missing-font warnings on clusters
                "font.family": "DejaVu Sans Mono",
                "font.sans-serif": ["DejaVu Sans Mono", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "Courier New", "Arial"],
            })
            import matplotlib as mpl
            mpl.rcParams.update({
                "font.family": "DejaVu Sans Mono",
                "font.sans-serif": ["DejaVu Sans Mono", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "Courier New", "Arial"],
                "axes.titleweight": "bold",
                "axes.titlesize": 13,
                "axes.labelsize": 11,
                "xtick.labelsize": 10,
                "ytick.labelsize": 10,
            })
            fig, ax = plt.subplots(figsize=(7.5, 4.5))
            accent = "#f97316"   # warm orange
            line = "#fb923c"
            sns.lineplot(data=df_out, x='threshold', y='avg_edges_per_new_edge_name',
                         marker="o", linewidth=2.9, color=line, ax=ax, markerfacecolor=accent,
                         markeredgecolor="#0b0f16", markeredgewidth=0.8)
            for x, y in zip(df_out['threshold'], df_out['avg_edges_per_new_edge_name']):
                ax.text(x, y, f"{y:.2f}", ha='center', va='bottom', fontsize=9, color="#f8fafc",
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="#111827", ec="#fb923c", alpha=0.8))
            ax.set_xlabel(f"Cosine {'distance' if args.distance_mode else 'similarity'} threshold")
            ax.set_ylabel("Avg edges per new edge name")
            ax.set_title("Avg number of edges per new edge name", color="#e2e8f0", fontsize=13, fontweight="bold")
            fig.tight_layout()
            seaborn_path = out_path.with_name(out_path.stem + "_seaborn.png")
            fig.savefig(seaborn_path, bbox_inches="tight", dpi=190)
            print(f"Wrote {seaborn_path}")
        except Exception as e:
            print(f"Seaborn plot skipped: {e}")

    # Visualization: neon/tech style
    try:
        import matplotlib.pyplot as plt
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        xs = df_out['threshold']
        ys = df_out['avg_edges_per_new_edge_name']
        ax.plot(xs, ys, marker='o', markersize=8, linewidth=2.6,
                color='#7ee0ff', markerfacecolor='#0ff', markeredgecolor='#7ee0ff', alpha=0.9)
        for x, y in zip(xs, ys):
            ax.text(x, y, f"{y:.2f}", ha='center', va='bottom', fontsize=9, fontweight='bold',
                    color='#f8fafc',
                    bbox=dict(boxstyle="round,pad=0.25", fc="#111827", ec="#22d3ee", alpha=0.8))
        ax.set_xlabel(f"Cosine {'distance' if args.distance_mode else 'similarity'} threshold", fontsize=11, color='#e2e8f0')
        ax.set_ylabel("Avg edges per new edge name", fontsize=11, color='#e2e8f0')
        ax.set_title("Canonical edge load vs threshold", fontsize=13, fontweight='bold', color='#7ee0ff')
        ax.tick_params(colors='#cbd5e1', labelsize=10)
        ax.grid(color='#1f2937', alpha=0.6)
        fig.tight_layout()
        plot_path = out_path.with_suffix(".png")
        fig.savefig(plot_path, bbox_inches='tight', dpi=190)
        print(f"Wrote {plot_path}")
    except Exception as e:
        print(f"Plot skipped (matplotlib missing or error): {e}")

    # Optional Plotly (NASA/JPL vibe) interactive HTML
    if args.plotly:
        try:
            import plotly.graph_objects as go
            import plotly.io as pio
            xs = df_out['threshold']
            ys = df_out['avg_edges_per_new_edge_name']
            mode_label = "distance" if args.distance_mode else "similarity"
            line_color = "#7ef3ff"
            glow_color = "rgba(126, 243, 255, 0.2)"
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines+markers+text",
                text=[f"{y:.2f}" for y in ys],
                textposition="top center",
                marker=dict(size=10, color=line_color, line=dict(color="#0ff", width=2)),
                line=dict(color=line_color, width=3),
                hovertemplate=f"{mode_label}=%{{x}}<br>avg=%{{y:.3f}}<extra></extra>"
            ))
            fig.update_layout(
                template=None,
                title="Avg number of edges per new edge name",
                xaxis_title=f"Cosine {mode_label} threshold",
                yaxis_title="Avg edges per new edge name",
                font=dict(color="#e5ecf4", family="Monaco, 'DejaVu Sans Mono', Menlo, Consolas, 'Courier New'"),
                plot_bgcolor="#050714",
                paper_bgcolor="#050714",
                xaxis=dict(gridcolor="#0c1224", zerolinecolor="#1b2340"),
                yaxis=dict(gridcolor="#0c1224", zerolinecolor="#1b2340"),
                margin=dict(l=60, r=40, t=60, b=60),
                shapes=[dict(type="rect", x0=min(xs), x1=max(xs), y0=min(ys)*0.9, y1=max(ys)*1.1,
                             fillcolor=glow_color, line=dict(width=0), layer="below")]
            )
            base_out = Path(args.out)
            plotly_path = base_out.with_suffix(".html")
            if args.plotly_static:
                png_path = base_out.with_name(base_out.stem + "_plotly.png")
                try:
                    fig.write_image(png_path, format="png", scale=2)
                    print(f"Wrote {png_path} (static Plotly PNG)")
                except Exception as ie:
                    print(f"Static Plotly export failed (need 'kaleido' installed): {ie}")
            fig.write_html(plotly_path, include_plotlyjs="cdn")
            print(f"Wrote {plotly_path} (HTML)")
        except Exception as e:
            print(f"Plotly output skipped: {e}")

    # Optional Bokeh interactive plot
    if args.bokeh:
        try:
            from bokeh.plotting import figure, output_file, save
            from bokeh.models import ColumnDataSource, HoverTool
            source = ColumnDataSource(df_out)
            mode_label = "distance" if args.distance_mode else "similarity"
            p = figure(width=750, height=420, background_fill_color="#0b1224",
                       title="Avg number of edges per new edge name",
                       tools="pan,wheel_zoom,reset,save,hover")
            p.title.text_color = "#7ee0ff"
            p.xaxis.axis_label = f"Cosine {mode_label} threshold"
            p.yaxis.axis_label = "Avg edges per new edge name"
            p.xaxis.axis_label_text_color = "#e2e8f0"
            p.yaxis.axis_label_text_color = "#e2e8f0"
            p.xaxis.major_label_text_color = "#cbd5e1"
            p.yaxis.major_label_text_color = "#cbd5e1"
            p.grid.grid_line_color = "#18233a"
            p.line('threshold', 'avg_edges_per_new_edge_name', source=source, line_width=3,
                   color="#7ef3ff")
            p.circle('threshold', 'avg_edges_per_new_edge_name', source=source, size=8,
                     fill_color="#0ff", line_color="#7ee0ff", line_width=2)
            hover = p.select_one(HoverTool)
            hover.tooltips = [
                (f"{mode_label}", "@threshold"),
                ("avg edges/new name", "@avg_edges_per_new_edge_name{0.000}"),
                ("representatives", "@representatives"),
                ("file", "@file")
            ]
            bokeh_path = out_path.with_suffix(".bokeh.html")
            output_file(bokeh_path)
            save(p)
            print(f"Wrote {bokeh_path}")
        except Exception as e:
            print(f"Bokeh output skipped: {e}")


if __name__ == '__main__':
    main()
