#!/usr/bin/env python3
"""
Firefighting Events Statistics Calculator
Calculates statistics from firefighting event data exported from the system.
"""

import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from pathlib import Path
import csv
import unicodedata
import urllib.request
import urllib.parse
import sys

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except ImportError:
    ZONEINFO_AVAILABLE = False
    # Fallback for Python < 3.9
    try:
        import pytz
        PYTZ_AVAILABLE = True
    except ImportError:
        PYTZ_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class EventStatistics:
    BASE_URL = 'http://webohled.hzsmsk.cz/api'
    # Backend stores times in CET/CEST but marks them as UTC
    BACKEND_TIMEZONE = 'Europe/Prague'

    def __init__(self, events_file='udalosti.json', types_file='typy.json', subtypes_file='podtypy.json', states_file='stavy.json'):
        """Initialize with data files."""
        self.events = self._load_json(events_file)
        self.types = {t['id']: self._format_name(t['nazev']) for t in self._load_json(types_file)}
        self.subtypes = {s['id']: self._format_name(s['nazev']) for s in self._load_json(subtypes_file)}
        self.states = {s['id']: self._format_name(s['nazev']) for s in self._load_json(states_file)}

    @staticmethod
    def _get_prague_tz():
        """Get Prague timezone object."""
        if ZONEINFO_AVAILABLE:
            return ZoneInfo('Europe/Prague')
        elif PYTZ_AVAILABLE:
            return pytz.timezone('Europe/Prague')
        else:
            # Fallback: assume CET (UTC+1) without DST handling
            # This is not perfect but works for most cases
            return timezone(timedelta(hours=1))

    @classmethod
    def _local_to_utc(cls, dt_str):
        """
        Convert Czech local time string to UTC for backend.

        Example: 2025-01-01 00:00 (CET) -> 2024-12-31 23:00 UTC
                 2025-07-01 00:00 (CEST) -> 2025-06-30 22:00 UTC
        """
        # Parse as naive datetime
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', ''))
        else:
            dt = datetime.fromisoformat(dt_str)

        # Make it timezone-aware in Prague time
        prague_tz = cls._get_prague_tz()

        if ZONEINFO_AVAILABLE or PYTZ_AVAILABLE:
            if ZONEINFO_AVAILABLE:
                dt_local = dt.replace(tzinfo=prague_tz)
            else:  # pytz
                dt_local = prague_tz.localize(dt)

            # Convert to UTC
            dt_utc = dt_local.astimezone(timezone.utc)
            return dt_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        else:
            # Simple fallback: subtract 1 hour (CET offset, doesn't handle DST)
            dt_utc = dt - timedelta(hours=1)
            return dt_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    @classmethod
    def _utc_to_local(cls, dt_utc):
        """
        Convert UTC datetime to Czech local time for analysis.

        Example: 2024-12-31 23:00 UTC -> 2025-01-01 00:00 CET
        """
        prague_tz = cls._get_prague_tz()

        if ZONEINFO_AVAILABLE or PYTZ_AVAILABLE:
            # Convert to Prague time
            dt_local = dt_utc.astimezone(prague_tz)
            return dt_local
        else:
            # Simple fallback: add 1 hour (doesn't handle DST)
            return dt_utc + timedelta(hours=1)

    @staticmethod
    def _format_name(name):
        """Convert uppercase names to more natural sentence case."""
        if not name:
            return name

        # List of acronyms that should remain uppercase
        acronyms = ['LDN', 'ZOC', 'OS', 'ZPP', 'SSU', 'VZ', 'IVC', 'HZS', 'SDL', 'NVZ', 'PRM', 'AED']

        # Convert to lowercase first
        formatted = name.lower()

        # Capitalize first letter
        formatted = formatted[0].upper() + formatted[1:]

        # Restore acronyms to uppercase
        for acronym in acronyms:
            # Match whole words only (surrounded by spaces, commas, or at start/end)
            import re
            pattern = r'\b' + acronym.lower() + r'\b'
            formatted = re.sub(pattern, acronym, formatted, flags=re.IGNORECASE)

        return formatted

    @classmethod
    def _strip_accents(cls, source):
        return ''.join(
            c for c in unicodedata.normalize('NFD', source)
            if unicodedata.category(c) != 'Mn'
        )

    @classmethod
    def _normalize(cls, source):
        return cls._strip_accents(source).lower().strip()

    @classmethod
    def _best_unit_match(
        cls,
        unit_name,
        units,
        name_key='nazev',
        cutoff=0.8
    ):
        target = cls._normalize(unit_name)
        best_item, best_score = None, 0.0

        for item in units:
            name = item.get(name_key, '')
            score = SequenceMatcher(None, target, cls._normalize(name)).ratio()
            if cls._normalize(name) == target:
                return (item, 1.0)
            if (score > best_score or
                (score == best_score and best_item is not None and len(name) < len(best_item.get(name_key, '')))):
                best_item, best_score = item, score

        return (best_item, best_score) if best_item and best_score >= cutoff else None

    @classmethod
    def unit_id_by_name(cls, unit_name):
        print("  Hledám ID jednotky...")
        params = urllib.parse.urlencode({"term": unit_name})
        units = cls._download_json(f'{cls.BASE_URL}/jednotky?{params}')
        if len(units) == 0:
            print('Nenalezeny žádné jednotky tohoto jména.')
            sys.exit(1)
        elif len(units) == 1:
            print(f'  Nalezena jednotka {units[0]["nazev"]} - ID {units[0]["id"]}')
            return units[0]['id']
        else:
            result = cls._best_unit_match(unit_name, units)
            if result:
                print(f'  Nalezena jednotka {result[0]["nazev"]} - ID {result[0]["id"]}')
                return result[0]['id']
            else:
                print('Něco se nepovedlo')
                sys.exit(1)

    @classmethod
    def from_web(cls, from_date, to_date, unit_id, save_to_files=False):
        """
        Initialize by downloading data from the web.

        Args:
            from_date: Start date in format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.SSSZ
            to_date: End date in format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.SSSZ
            unit_id: Unit ID (e.g., 8102157)
            save_to_files: If True, save downloaded data to local JSON files
        """
        print("Stahuji data z webu...")

        # Download enumerator files
        print("  Stahuji typy...")
        types_data = cls._download_json(f'{cls.BASE_URL}/typy')

        print("  Stahuji podtypy...")
        subtypes_data = cls._download_json(f'{cls.BASE_URL}/podtypy')

        print("  Stahuji stavy...")
        states_data = cls._download_json(f'{cls.BASE_URL}/stavy')

        # Get all state IDs for the events query
        state_ids = [s['id'] for s in states_data]

        # Normalize date formats (add time if not present)
        if 'T' not in from_date:
            from_date_local = f'{from_date}T00:00:00'
        else:
            from_date_local = from_date.replace('Z', '')

        if 'T' not in to_date:
            to_date_local = f'{to_date}T23:59:59'
        else:
            to_date_local = to_date.replace('Z', '')

        # Convert Czech local times to UTC for backend
        from_date_utc = cls._local_to_utc(from_date_local)
        to_date_utc = cls._local_to_utc(to_date_local)

        # Build events URL
        params = {
            'casOd': from_date_utc,
            'casDo': to_date_utc,
            'jednotkaId': unit_id,
            'background': 'true',
        }

        # Add all state IDs
        url_parts = [f'{cls.BASE_URL}/?']
        url_parts.append(urllib.parse.urlencode(params))
        for state_id in state_ids:
            url_parts.append(f'&stavIds={state_id}')

        events_url = ''.join(url_parts)

        print(f"  Český čas: {from_date_local.replace('T', ' ')} až {to_date_local.replace('T', ' ')}")
        print(f"  UTC dotaz: {from_date_utc} až {to_date_utc}")
        print(f"  Stahuji události...")
        events_data = cls._download_json(events_url)

        print(f"Staženo {len(events_data)} událostí\n")

        # Save to files if requested
        if save_to_files:
            print("Ukládám stažená data do lokálních souborů...")
            cls._save_json('typy.json', types_data)
            cls._save_json('podtypy.json', subtypes_data)
            cls._save_json('stavy.json', states_data)
            cls._save_json('udalosti.json', events_data)
            print("Data uložena do: typy.json, podtypy.json, stavy.json, udalosti.json\n")

        # Create instance with downloaded data
        instance = cls.__new__(cls)
        instance.events = events_data
        instance.types = {t['id']: cls._format_name(t['nazev']) for t in types_data}
        instance.subtypes = {s['id']: cls._format_name(s['nazev']) for s in subtypes_data}
        instance.states = {s['id']: cls._format_name(s['nazev']) for s in states_data}

        return instance

    @staticmethod
    def _download_json(url):
        """Download JSON data from URL."""
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))

    @staticmethod
    def _save_json(filename, data):
        """Save JSON data to file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_json(self, filename):
        """Load JSON file."""
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_datetime(self, date_str):
        """Parse ISO datetime string and convert to Czech local time."""
        if date_str:
            dt_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Convert UTC to Czech local time for analysis
            return self._utc_to_local(dt_utc)
        return None

    def calculate_all_statistics(self):
        """Calculate all statistics and return results."""
        stats = {
            'total_events': len(self.events),
            'by_type': self._stats_by_type(),
            'by_subtype': self._stats_by_subtype(),
            'by_month': self._stats_by_month(),
            'by_quarter': self._stats_by_quarter(),
            'by_state': self._stats_by_state(),
            'by_day_of_week': self._stats_by_day_of_week(),
            'by_hour': self._stats_by_hour(),
            'zoc_events': self._stats_zoc(),
        }
        return stats

    def _stats_by_type(self):
        """Count events by type."""
        type_counts = Counter()
        for event in self.events:
            type_id = event.get('typId')
            type_name = self.types.get(type_id, f'Unknown ({type_id})')
            type_counts[type_name] += 1
        return dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True))

    def _stats_by_subtype(self):
        """Count events by subtype, grouped by type."""
        subtype_stats = defaultdict(Counter)
        for event in self.events:
            type_id = event.get('typId')
            subtype_id = event.get('podtypId')
            type_name = self.types.get(type_id, f'Unknown ({type_id})')
            subtype_name = self.subtypes.get(subtype_id, f'Unknown ({subtype_id})')
            subtype_stats[type_name][subtype_name] += 1

        # Convert to regular dict and sort
        result = {}
        for type_name in sorted(subtype_stats.keys()):
            result[type_name] = dict(sorted(
                subtype_stats[type_name].items(),
                key=lambda x: x[1],
                reverse=True
            ))
        return result

    def _stats_by_month(self):
        """Count events by month."""
        if not self.events:
            return {}

        # Find date range
        dates = [self._parse_datetime(e.get('casOhlaseni')) for e in self.events]
        dates = [d for d in dates if d]
        if not dates:
            return {}

        min_date = min(dates)
        max_date = max(dates)

        # Count events by month
        month_counts = defaultdict(int)
        for event in self.events:
            dt = self._parse_datetime(event.get('casOhlaseni'))
            if dt:
                month_key = dt.strftime('%Y-%m')
                month_counts[month_key] += 1

        # Fill in all months in the range
        result = {}
        current = min_date.replace(day=1)
        while current <= max_date:
            month_key = current.strftime('%Y-%m')
            result[month_key] = month_counts.get(month_key, 0)
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return result

    def _stats_by_quarter(self):
        """Count events by quarter."""
        if not self.events:
            return {}

        # Find date range
        dates = [self._parse_datetime(e.get('casOhlaseni')) for e in self.events]
        dates = [d for d in dates if d]
        if not dates:
            return {}

        min_date = min(dates)
        max_date = max(dates)

        # Count events by quarter
        quarter_counts = defaultdict(int)
        for event in self.events:
            dt = self._parse_datetime(event.get('casOhlaseni'))
            if dt:
                quarter = (dt.month - 1) // 3 + 1
                quarter_key = f'{dt.year}-Q{quarter}'
                quarter_counts[quarter_key] += 1

        # Fill in all quarters in the range
        result = {}
        current_year = min_date.year
        current_quarter = (min_date.month - 1) // 3 + 1
        max_year = max_date.year
        max_quarter = (max_date.month - 1) // 3 + 1

        while current_year < max_year or (current_year == max_year and current_quarter <= max_quarter):
            quarter_key = f'{current_year}-Q{current_quarter}'
            result[quarter_key] = quarter_counts.get(quarter_key, 0)
            current_quarter += 1
            if current_quarter > 4:
                current_quarter = 1
                current_year += 1

        return result

    def _stats_by_state(self):
        """Count events by state (stavId)."""
        state_counts = Counter()
        for event in self.events:
            state_id = event.get('stavId')
            state_name = self.states.get(state_id, f'Unknown ({state_id})')
            state_counts[state_name] += 1
        return dict(sorted(state_counts.items(), key=lambda x: x[1], reverse=True))

    def _stats_by_day_of_week(self):
        """Count events by day of week."""
        day_names = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']
        day_counts = defaultdict(int)
        for event in self.events:
            dt = self._parse_datetime(event.get('casOhlaseni'))
            if dt:
                day_counts[day_names[dt.weekday()]] += 1

        # Return in week order
        return {day: day_counts[day] for day in day_names}

    def _stats_by_hour(self):
        """Count events by hour of day."""
        hour_counts = defaultdict(int)
        for event in self.events:
            dt = self._parse_datetime(event.get('casOhlaseni'))
            if dt:
                hour_counts[dt.hour] += 1

        # Return all 24 hours with counts (0-23)
        return {hour: hour_counts.get(hour, 0) for hour in range(24)}

    def _stats_zoc(self):
        """Count ZOC (special response) events."""
        zoc_count = sum(1 for event in self.events if event.get('zoc', False))
        return {
            'total_zoc': zoc_count,
            'total_non_zoc': len(self.events) - zoc_count,
            'percentage_zoc': round(zoc_count / len(self.events) * 100, 2) if self.events else 0
        }

    def print_statistics(self, stats):
        """Print statistics in a readable format."""
        print("=" * 80)
        print("STATISTIKY UDÁLOSTÍ HASIČŮ")
        print("=" * 80)
        print(f"\nCelkem událostí: {stats['total_events']}\n")

        print("-" * 80)
        print("UDÁLOSTI PODLE TYPU")
        print("-" * 80)
        for type_name, count in stats['by_type'].items():
            percentage = (count / stats['total_events'] * 100) if stats['total_events'] else 0
            print(f"{type_name:.<50} {count:>5} ({percentage:>5.1f}%)")

        print("\n" + "-" * 80)
        print("UDÁLOSTI PODLE PODTYPU (seskupeno podle typu)")
        print("-" * 80)
        for type_name, subtypes in stats['by_subtype'].items():
            print(f"\n{type_name}:")
            for subtype_name, count in subtypes.items():
                print(f"  {subtype_name:.<48} {count:>5}")

        print("\n" + "-" * 80)
        print("ROZLOŽENÍ PO MĚSÍCÍCH")
        print("-" * 80)
        for month, count in stats['by_month'].items():
            print(f"{month:.<50} {count:>5}")

        print("\n" + "-" * 80)
        print("ROZLOŽENÍ PO ČTVRTLETÍCH")
        print("-" * 80)
        for quarter, count in stats['by_quarter'].items():
            print(f"{quarter:.<50} {count:>5}")

        print("\n" + "-" * 80)
        print("ROZLOŽENÍ PO DNECH V TÝDNU")
        print("-" * 80)
        for day, count in stats['by_day_of_week'].items():
            percentage = (count / stats['total_events'] * 100) if stats['total_events'] else 0
            print(f"{day:.<50} {count:>5} ({percentage:>5.1f}%)")

        print("\n" + "-" * 80)
        print("ROZLOŽENÍ PO HODINÁCH")
        print("-" * 80)
        for hour, count in stats['by_hour'].items():
            bar = '█' * int(count / max(stats['by_hour'].values()) * 40) if stats['by_hour'].values() else ''
            print(f"{hour:02d}:00 {count:>5} {bar}")

        print("\n" + "-" * 80)
        print("UDÁLOSTI ZOC (Zpráva o činnosti)")
        print("-" * 80)
        print(f"Události ZOC:....................................... {stats['zoc_events']['total_zoc']:>5}")
        print(f"Události bez ZOC:................................... {stats['zoc_events']['total_non_zoc']:>5}")
        print(f"Procento ZOC:....................................... {stats['zoc_events']['percentage_zoc']:>5.1f}%")

        print("\n" + "-" * 80)
        print("UDÁLOSTI PODLE STAVU")
        print("-" * 80)
        for state_name, count in stats['by_state'].items():
            percentage = (count / stats['total_events'] * 100) if stats['total_events'] else 0
            print(f"{state_name:.<50} {count:>5} ({percentage:>5.1f}%)")

        print("\n" + "=" * 80)

    def export_to_csv(self, stats, output_dir='.'):
        """Export statistics to CSV files."""
        output_path = Path(output_dir)

        # Export by type
        with open(output_path / 'stats_by_type.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Typ', 'Počet'])
            for type_name, count in stats['by_type'].items():
                writer.writerow([type_name, count])

        # Export by subtype
        with open(output_path / 'stats_by_subtype.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Typ', 'Podtyp', 'Počet'])
            for type_name, subtypes in stats['by_subtype'].items():
                for subtype_name, count in subtypes.items():
                    writer.writerow([type_name, subtype_name, count])

        # Export monthly
        with open(output_path / 'stats_by_month.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Měsíc', 'Počet'])
            for month, count in stats['by_month'].items():
                writer.writerow([month, count])

        # Export hourly
        with open(output_path / 'stats_by_hour.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Hodina', 'Počet'])
            for hour, count in stats['by_hour'].items():
                writer.writerow([hour, count])

        # Export by state
        with open(output_path / 'stats_by_state.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Stav', 'Počet'])
            for state_name, count in stats['by_state'].items():
                writer.writerow([state_name, count])

        print(f"\nCSV soubory exportovány do: {output_path.absolute()}")

    def export_to_json(self, stats, filename='statistics.json'):
        """Export all statistics to a JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\nJSON exportován do: {Path(filename).absolute()}")

    def export_plots(self, stats, output_dir='.'):
        """Generate and export plots as PNG images."""
        if not MATPLOTLIB_AVAILABLE:
            print("\nChyba: matplotlib není nainstalován. Pro vytvoření grafů nainstalujte matplotlib:", file=sys.stderr)
            print("  pip install matplotlib", file=sys.stderr)
            return

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Set Czech font if available, otherwise use default
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 10

        print("\nGeneruji grafy...")

        # 1. Events by Type - Horizontal Bar Chart
        if stats['by_type']:
            fig, ax = plt.subplots(figsize=(10, 6))
            types = list(stats['by_type'].keys())
            counts = list(stats['by_type'].values())
            colors = plt.cm.Set3(range(len(types)))

            bars = ax.barh(types, counts, color=colors)
            ax.set_xlabel('Počet událostí')
            ax.set_title('Události podle typu', fontsize=14, fontweight='bold')
            ax.grid(axis='x', alpha=0.3)

            # Add count labels on bars
            for bar in bars:
                width = bar.get_width()
                ax.text(width, bar.get_y() + bar.get_height()/2,
                       f' {int(width)}', ha='left', va='center')

            plt.tight_layout()
            plt.savefig(output_path / 'graf_typy.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_typy.png")

        # 2. Monthly Distribution - Line Chart
        if stats['by_month']:
            fig, ax = plt.subplots(figsize=(12, 6))
            months = list(stats['by_month'].keys())
            counts = list(stats['by_month'].values())

            ax.plot(months, counts, marker='o', linewidth=2, markersize=8, color='#2E86AB')
            ax.fill_between(range(len(months)), counts, alpha=0.3, color='#2E86AB')
            ax.set_xlabel('Měsíc')
            ax.set_ylabel('Počet událostí')
            ax.set_title('Rozložení událostí po měsících', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45, ha='right')

            # Add value labels on points
            for i, count in enumerate(counts):
                ax.text(i, count, f' {count}', ha='left', va='bottom')

            plt.tight_layout()
            plt.savefig(output_path / 'graf_mesice.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_mesice.png")

        # 3. Quarterly Distribution - Bar Chart
        if stats['by_quarter']:
            fig, ax = plt.subplots(figsize=(10, 6))
            quarters = list(stats['by_quarter'].keys())
            counts = list(stats['by_quarter'].values())

            bars = ax.bar(quarters, counts, color='#A23B72', width=0.6)
            ax.set_xlabel('Čtvrtletí')
            ax.set_ylabel('Počet událostí')
            ax.set_title('Rozložení událostí po čtvrtletích', fontsize=14, fontweight='bold')
            ax.grid(axis='y', alpha=0.3)

            # Add count labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, height,
                       f'{int(height)}', ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig(output_path / 'graf_ctvrtleti.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_ctvrtleti.png")

        # 4. Day of Week Distribution - Bar Chart
        if stats['by_day_of_week']:
            fig, ax = plt.subplots(figsize=(10, 6))
            days = list(stats['by_day_of_week'].keys())
            counts = list(stats['by_day_of_week'].values())
            colors_week = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DFE6E9', '#A8E6CF']

            bars = ax.bar(days, counts, color=colors_week)
            ax.set_xlabel('Den v týdnu')
            ax.set_ylabel('Počet událostí')
            ax.set_title('Rozložení událostí po dnech v týdnu', fontsize=14, fontweight='bold')
            ax.grid(axis='y', alpha=0.3)
            plt.xticks(rotation=45, ha='right')

            # Add count labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, height,
                       f'{int(height)}', ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig(output_path / 'graf_dny.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_dny.png")

        # 5. Hourly Distribution - Bar Chart
        if stats['by_hour']:
            fig, ax = plt.subplots(figsize=(14, 6))
            hours = list(stats['by_hour'].keys())
            counts = list(stats['by_hour'].values())

            # Color bars based on value (gradient)
            colors_hourly = plt.cm.YlOrRd([c/max(counts) if max(counts) > 0 else 0 for c in counts])

            bars = ax.bar(hours, counts, color=colors_hourly, width=0.8)
            ax.set_xlabel('Hodina')
            ax.set_ylabel('Počet událostí')
            ax.set_title('Rozložení událostí po hodinách', fontsize=14, fontweight='bold')
            ax.set_xticks(range(0, 24, 2))
            ax.set_xticklabels([f'{h}:00' for h in range(0, 24, 2)])
            ax.grid(axis='y', alpha=0.3)

            plt.tight_layout()
            plt.savefig(output_path / 'graf_hodiny.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_hodiny.png")

        # 6. Subtypes Distribution - Horizontal Bar Chart
        if stats['by_subtype']:
            # Flatten subtypes from all types and get top ones
            all_subtypes = []
            for type_name, subtypes in stats['by_subtype'].items():
                for subtype_name, count in subtypes.items():
                    all_subtypes.append((subtype_name, count, type_name))

            # Sort by count and take top 15
            all_subtypes.sort(key=lambda x: x[1], reverse=True)
            top_subtypes = all_subtypes[:15]

            if top_subtypes:
                fig, ax = plt.subplots(figsize=(12, 10))

                subtype_names = [item[0] for item in top_subtypes]
                counts = [item[1] for item in top_subtypes]
                type_names = [item[2] for item in top_subtypes]

                # Create color map based on parent type
                unique_types = list(dict.fromkeys(type_names))
                type_colors = {t: plt.cm.Set3(i/len(unique_types)) for i, t in enumerate(unique_types)}
                colors = [type_colors[t] for t in type_names]

                bars = ax.barh(subtype_names, counts, color=colors)
                ax.set_xlabel('Počet událostí')
                ax.set_title('Top 15 podtypů událostí', fontsize=14, fontweight='bold')
                ax.grid(axis='x', alpha=0.3)

                # Add count labels
                for bar in bars:
                    width = bar.get_width()
                    ax.text(width, bar.get_y() + bar.get_height()/2,
                           f' {int(width)}', ha='left', va='center')

                # Add legend for types
                from matplotlib.patches import Patch
                legend_elements = [Patch(facecolor=type_colors[t], label=t)
                                 for t in unique_types]
                ax.legend(handles=legend_elements, loc='lower right', fontsize=9)

                plt.tight_layout()
                plt.savefig(output_path / 'graf_podtypy.png', dpi=150, bbox_inches='tight')
                plt.close()
                print(f"  ✓ graf_podtypy.png")

        # 7. Top States - Horizontal Bar Chart
        if stats['by_state']:
            fig, ax = plt.subplots(figsize=(12, 8))
            # Take top 10 states
            items = list(stats['by_state'].items())[:10]
            states = [item[0] for item in items]
            counts = [item[1] for item in items]

            colors = plt.cm.viridis(range(len(states)))
            bars = ax.barh(states, counts, color=colors)
            ax.set_xlabel('Počet událostí')
            ax.set_title('Události podle stavu (top 10)', fontsize=14, fontweight='bold')
            ax.grid(axis='x', alpha=0.3)

            # Add count labels
            for bar in bars:
                width = bar.get_width()
                ax.text(width, bar.get_y() + bar.get_height()/2,
                       f' {int(width)}', ha='left', va='center')

            plt.tight_layout()
            plt.savefig(output_path / 'graf_stavy.png', dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ graf_stavy.png")

        print(f"\nGrafy uloženy do: {output_path.absolute()}")


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Výpočet statistik událostí hasičů',
        epilog='Příklady:\n'
               '  %(prog)s --from 2025-01-01 --to 2025-12-31 --id 8102157\n'
               '  %(prog)s --from 2025-01-01 --to 2025-12-31 --id 8102157 --save\n'
               '  %(prog)s --from 2025-01-01 --to 2025-12-31 --id 8102157 --export-csv --export-plots\n\n'
               '  %(prog)s --from 2025-01-01 --to 2025-12-31 --unit "Frýdek-Místek - Lískovec" --export-csv --export-plots\n\n'
               '  %(prog)s --export-plots (použije lokální JSON soubory a vytvoří grafy)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Web download options
    web_group = parser.add_argument_group('možnosti stahování z webu')
    web_group.add_argument('--from', dest='from_date', metavar='DATUM',
                          help='Počáteční datum (RRRR-MM-DD nebo RRRR-MM-DDTHH:MM:SS.SSSZ)')
    web_group.add_argument('--to', dest='to_date', metavar='DATUM',
                          help='Koncové datum (RRRR-MM-DD nebo RRRR-MM-DDTHH:MM:SS.SSSZ)')

    # options for unit selection - by ID or unit name
    unit_mux = web_group.add_mutually_exclusive_group(required=False)
    unit_mux.add_argument('--id', dest='unit_id', metavar='ID',
                        help='ID jednotky (např. 8102157)')
    unit_mux.add_argument('--unit', dest='unit_name', metavar='NÁZEV',
                        help='Název jednotky (např. "Frýdek-Místek - Lískovec")')


    web_group.add_argument('--save', action='store_true',
                          help='Uložit stažená data do lokálních JSON souborů pro pozdější použití')

    # Local file options
    file_group = parser.add_argument_group('možnosti lokálních souborů')
    file_group.add_argument('--events', default='udalosti.json',
                           help='JSON soubor s událostmi (výchozí: udalosti.json)')
    file_group.add_argument('--types', default='typy.json',
                           help='JSON soubor s typy (výchozí: typy.json)')
    file_group.add_argument('--subtypes', default='podtypy.json',
                           help='JSON soubor s podtypy (výchozí: podtypy.json)')
    file_group.add_argument('--states', default='stavy.json',
                           help='JSON soubor se stavy (výchozí: stavy.json)')

    # Export options
    export_group = parser.add_argument_group('možnosti exportu')
    export_group.add_argument('--export-csv', action='store_true',
                             help='Exportovat statistiky do CSV souborů')
    export_group.add_argument('--export-json', action='store_true',
                             help='Exportovat statistiky do JSON souboru')
    export_group.add_argument('--export-plots', action='store_true',
                             help='Vygenerovat grafy jako PNG obrázky (vyžaduje matplotlib)')

    args = parser.parse_args()

    # Check if we should download from web
    use_web = args.from_date or args.to_date or args.unit_id or args.unit_name

    if use_web:
        # Validate that all web parameters are provided
        if not (args.from_date and args.to_date and (args.unit_id or args.unit_name)):
            parser.error('Při stahování z webu jsou povinné parametry --from, --to a --id nebo --unit')

        if args.unit_name:
            unit_id = EventStatistics.unit_id_by_name(args.unit_name)
        else:
            unit_id = args.unit_id

        # Download from web
        calculator = EventStatistics.from_web(args.from_date, args.to_date, unit_id,
                                             save_to_files=args.save)
    else:
        # Use local files
        try:
            calculator = EventStatistics(args.events, args.types, args.subtypes, args.states)
        except FileNotFoundError as e:
            print(f"Chyba: {e}", file=sys.stderr)
            print("\nLokální datové soubory nenalezeny. Máte dvě možnosti:\n", file=sys.stderr)
            print("1. Stáhnout data z webu pomocí:", file=sys.stderr)
            print(f"   python3 {sys.argv[0]} --from RRRR-MM-DD --to RRRR-MM-DD --unit ID_JEDNOTKY", file=sys.stderr)
            print(f"\n   Příklad:", file=sys.stderr)
            print(f"   python3 {sys.argv[0]} --from 2025-01-01 --to 2025-12-31 --unit 8102157", file=sys.stderr)
            print("\n2. Nebo zajistit, že tyto soubory existují v aktuálním adresáři:", file=sys.stderr)
            print(f"   - {args.events}", file=sys.stderr)
            print(f"   - {args.types}", file=sys.stderr)
            print(f"   - {args.subtypes}", file=sys.stderr)
            print(f"   - {args.states}", file=sys.stderr)
            sys.exit(1)

    # Calculate statistics
    stats = calculator.calculate_all_statistics()

    # Print to console
    calculator.print_statistics(stats)

    # Export if requested
    if args.export_csv:
        calculator.export_to_csv(stats)

    if args.export_json:
        calculator.export_to_json(stats)

    if args.export_plots:
        calculator.export_plots(stats)


if __name__ == '__main__':
    main()
