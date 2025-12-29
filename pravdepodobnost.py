#!/usr/bin/env python3
"""
Pravděpodobnost událostí - Heatmapa
Vypočítá pravděpodobnost události pro kombinaci den v týdnu × část dne.
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class EventProbability:
    def __init__(self, events_file='udalosti.json'):
        """Initialize with events data file."""
        self.events = self._load_json(events_file)

    def _load_json(self, filename):
        """Load JSON file."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Chyba: Soubor {filename} nebyl nalezen.", file=sys.stderr)
            print(f"Nejprve spusťte: python3 statistiky.py --from DATUM --to DATUM --unit ID --save", file=sys.stderr)
            sys.exit(1)

    def _parse_datetime(self, date_str):
        """Parse ISO datetime string."""
        if date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return None

    def _get_day_part(self, hour):
        """Get part of day from hour (0-23)."""
        if 0 <= hour < 6:
            return 'Noc'
        elif 6 <= hour < 12:
            return 'Ráno'
        elif 12 <= hour < 18:
            return 'Odpoledne'
        else:  # 18-23
            return 'Večer'

    def _get_day_part_index(self, hour):
        """Get numeric index for day part (for heatmap)."""
        if 0 <= hour < 6:
            return 0  # Noc
        elif 6 <= hour < 12:
            return 1  # Ráno
        elif 12 <= hour < 18:
            return 2  # Odpoledne
        else:  # 18-23
            return 3  # Večer

    def calculate_probability(self):
        """Calculate probability for each day-of-week × day-part combination."""
        if not self.events:
            print("Chyba: Žádné události k analýze.", file=sys.stderr)
            sys.exit(1)

        # Parse all event dates
        event_dates = []
        for event in self.events:
            dt = self._parse_datetime(event.get('casOhlaseni'))
            if dt:
                event_dates.append(dt)

        if not event_dates:
            print("Chyba: Žádné platné datumy událostí.", file=sys.stderr)
            sys.exit(1)

        # Get date range
        min_date = min(event_dates)
        max_date = max(event_dates)
        total_days = (max_date - min_date).days + 1

        print(f"Analyzuji data od {min_date.date()} do {max_date.date()}")
        print(f"Celkem dní: {total_days}")
        print(f"Celkem událostí: {len(event_dates)}\n")

        # Count events for each combination
        day_names = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']
        day_parts = ['Noc', 'Ráno', 'Odpoledne', 'Večer']

        event_counts = defaultdict(int)

        for dt in event_dates:
            day_name = day_names[dt.weekday()]
            day_part = self._get_day_part(dt.hour)
            key = (day_name, day_part)
            event_counts[key] += 1

        # Calculate how many of each combination occurred in the period
        # Each day has 4 parts, so we need to count how many times each day occurred
        day_occurrences = defaultdict(int)
        current = min_date.replace(hour=0, minute=0, second=0, microsecond=0)

        while current <= max_date:
            day_name = day_names[current.weekday()]
            day_occurrences[day_name] += 1
            current += timedelta(days=1)

        # Calculate probabilities
        # Each day occurrence has 4 day parts
        probabilities = {}

        for day_name in day_names:
            for day_part in day_parts:
                key = (day_name, day_part)
                event_count = event_counts[key]
                # Number of times this combination could have occurred
                opportunities = day_occurrences[day_name]  # Each day has this day part

                if opportunities > 0:
                    probability = (event_count / opportunities) * 100
                    probabilities[key] = {
                        'count': event_count,
                        'opportunities': opportunities,
                        'probability': probability
                    }
                else:
                    probabilities[key] = {
                        'count': 0,
                        'opportunities': 0,
                        'probability': 0.0
                    }

        return probabilities, day_names, day_parts, min_date, max_date

    def print_probability_table(self, probabilities, day_names, day_parts):
        """Print probability table to console."""
        print("=" * 105)
        print("PRAVDĚPODOBNOST UDÁLOSTI: DEN V TÝDNU × ČÁST DNE")
        print("=" * 105)
        print()

        # Print time ranges legend
        print("Části dne:")
        print("  Noc:       0:00 -  6:00")
        print("  Ráno:      6:00 - 12:00")
        print("  Odpoledne: 12:00 - 18:00")
        print("  Večer:     18:00 - 24:00")
        print()

        # Define day parts with time ranges for header
        day_part_labels = {
            'Noc': 'Noc (0-6h)',
            'Ráno': 'Ráno (6-12h)',
            'Odpoledne': 'Odpoledne (12-18h)',
            'Večer': 'Večer (18-24h)'
        }

        # Print header
        print(f"{'Den':.<15}", end='')
        for day_part in day_parts:
            label = day_part_labels.get(day_part, day_part)
            print(f"{label:>20}", end='')
        print()
        print("-" * 105)

        # Print data
        for day_name in day_names:
            print(f"{day_name:.<15}", end='')
            for day_part in day_parts:
                key = (day_name, day_part)
                data = probabilities[key]
                prob = data['probability']
                count = data['count']

                # Format: probability% (count)
                print(f"{prob:>6.2f}% ({count:>2})", end='     ')
            print()

        print()

        # Find highest and lowest probabilities
        sorted_probs = sorted(probabilities.items(), key=lambda x: x[1]['probability'], reverse=True)

        print("=" * 105)
        print("PŘEHLED")
        print("=" * 105)

        avg_prob = sum(p['probability'] for p in probabilities.values()) / len(probabilities)
        total_events = sum(p['count'] for p in probabilities.values())

        print(f"Průměrná pravděpodobnost: {avg_prob:.2f}%")
        print(f"Celkem událostí: {total_events}")
        print()

        # Time range mapping for display
        time_ranges = {
            'Noc': '0-6h',
            'Ráno': '6-12h',
            'Odpoledne': '12-18h',
            'Večer': '18-24h'
        }

        print("Top 5 nejrizikovějších kombinací:")
        for i, (key, data) in enumerate(sorted_probs[:5], 1):
            day_name, day_part = key
            time_range = time_ranges.get(day_part, '')
            print(f"  {i}. {day_name} {day_part} ({time_range}){' ' * (30 - len(day_name) - len(day_part) - len(time_range))} {data['probability']:>6.2f}% ({data['count']} událostí)")

        print()
        print("Top 5 nejbezpečnějších kombinací:")
        for i, (key, data) in enumerate(sorted_probs[-5:][::-1], 1):
            day_name, day_part = key
            time_range = time_ranges.get(day_part, '')
            print(f"  {i}. {day_name} {day_part} ({time_range}){' ' * (30 - len(day_name) - len(day_part) - len(time_range))} {data['probability']:>6.2f}% ({data['count']} událostí)")

        print()
        print("=" * 105)

    def create_heatmap(self, probabilities, day_names, day_parts, min_date, max_date, output_file='heatmapa_pravdepodobnost.png'):
        """Create and save heatmap visualization."""
        if not MATPLOTLIB_AVAILABLE:
            print("\nChyba: matplotlib není nainstalován. Heatmapa nebyla vytvořena.", file=sys.stderr)
            print("Pro vytvoření grafu nainstalujte matplotlib: pip install matplotlib", file=sys.stderr)
            return

        # Create matrix for heatmap (days × day_parts)
        matrix = np.zeros((len(day_names), len(day_parts)))

        for i, day_name in enumerate(day_names):
            for j, day_part in enumerate(day_parts):
                key = (day_name, day_part)
                matrix[i][j] = probabilities[key]['probability']

        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))

        # Create heatmap
        im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')

        # Define labels with time ranges
        day_part_labels_with_time = [
            'Noc\n(0-6h)',
            'Ráno\n(6-12h)',
            'Odpoledne\n(12-18h)',
            'Večer\n(18-24h)'
        ]

        # Set ticks
        ax.set_xticks(np.arange(len(day_parts)))
        ax.set_yticks(np.arange(len(day_names)))
        ax.set_xticklabels(day_part_labels_with_time)
        ax.set_yticklabels(day_names)

        # Rotate the tick labels for better readability
        plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=11)

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Pravděpodobnost (%)', rotation=270, labelpad=20)

        # Add text annotations
        for i in range(len(day_names)):
            for j in range(len(day_parts)):
                day_name = day_names[i]
                day_part = day_parts[j]
                key = (day_name, day_part)
                prob = probabilities[key]['probability']
                count = probabilities[key]['count']

                text = f'{prob:.1f}%\n({count})'
                color = 'white' if prob > matrix.max() * 0.6 else 'black'
                ax.text(j, i, text, ha="center", va="center", color=color, fontsize=10, fontweight='bold')

        # Set labels and title
        ax.set_xlabel('Část dne', fontsize=12, fontweight='bold')
        ax.set_ylabel('Den v týdnu', fontsize=12, fontweight='bold')

        title = f'Pravděpodobnost události\n{min_date.date()} - {max_date.date()}'
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        # Grid
        ax.set_xticks(np.arange(len(day_parts))+0.5, minor=True)
        ax.set_yticks(np.arange(len(day_names))+0.5, minor=True)
        ax.grid(which="minor", color="white", linestyle='-', linewidth=2)

        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"\nHeatmapa uložena: {output_file}")


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Výpočet pravděpodobnosti události podle dne a času',
        epilog='Příklad:\n  %(prog)s\n  %(prog)s --events data/udalosti.json',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--events', default='udalosti.json',
                       help='JSON soubor s událostmi (výchozí: udalosti.json)')
    parser.add_argument('--output', default='heatmapa_pravdepodobnost.png',
                       help='Výstupní soubor pro heatmapu (výchozí: heatmapa_pravdepodobnost.png)')

    args = parser.parse_args()

    # Calculate probabilities
    calculator = EventProbability(args.events)
    probabilities, day_names, day_parts, min_date, max_date = calculator.calculate_probability()

    # Print table
    calculator.print_probability_table(probabilities, day_names, day_parts)

    # Create heatmap
    calculator.create_heatmap(probabilities, day_names, day_parts, min_date, max_date, args.output)


if __name__ == '__main__':
    main()
