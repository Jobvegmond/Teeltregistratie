"""Tests voor database.lees_energie_csv: welke regels warmte en gas zijn, per tuin."""
import io
import unittest
from datetime import date

import database

CSV = """label;pcu;type_1;idx_1;type_2;idx_2;startdate;enddate;value
Sum_24h_HXEnergy;Matricaria25;Warmtewis.;1;;;8-1-26;8-1-26;0
Sum_24h_HXEnergy;Matricaria25;Warmtewis.;1;;;10-1-26;10-1-26;1000
Sum_24h_PtEnergyUse;Matricaria25;Pulsteller;1;;;10-1-26;10-1-26;12,5
Sum_24h_PtEnergyUse;Matricaria25;Pulsteller;2;;;10-1-26;10-1-26;3
Sum_24h_PtEnergyUse;Matricaria25;Pulsteller;2;;;10-1-26;10-1-26;1
"""


class TestEnergieCsv(unittest.TestCase):
    def test_tuin1_warmtewisselaar_in_kwh(self):
        warmte, gas, _ = database.lees_energie_csv(io.StringIO(CSV), 1)
        # 1000 kWh = 3600 MJ; 8 januari valt vóór de start van de meting.
        self.assertEqual(warmte, {date(2026, 1, 10): 3600.0})
        self.assertEqual(gas, {date(2026, 1, 10): 12.5})

    def test_tuin3_pulsteller_in_gj(self):
        warmte, gas, _ = database.lees_energie_csv(io.StringIO(CSV), 3)
        # Pulsteller 2 in GJ, twee regels op één dag opgeteld: 4 GJ = 4000 MJ.
        self.assertEqual(warmte, {date(2026, 1, 10): 4000.0})
        self.assertEqual(gas, {date(2026, 1, 10): 12.5})


if __name__ == "__main__":
    unittest.main()
