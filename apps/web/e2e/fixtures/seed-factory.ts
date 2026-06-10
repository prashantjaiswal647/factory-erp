// Deterministic seed factory for synthetic pilot smoke test
// Uses fixed seed for repeatable test data

export interface SeedFactory {
  factoryId: string;
  factoryName: string;
  ownerPhone: string;
  email: string;
  password: string;
  address: string;
  gstin: string;
  masterData: {
    products: Array<{ name: string; size: string; variety: string }>;
    rawMaterials: Array<{ name: string; unit: string }>;
    machines: Array<{ name: string; type: string }>;
    workers: Array<{ name: string; phone: string; wage: number }>;
  };
  inventory: Array<{ material: string; quantity: number; unitCost: number }>;
  production: Array<{ day: number; product: string; quantity: number; wastage: number }>;
  sales: Array<{ customer: string; product: string; quantity: number; rate: number }>;
}

export function createSeedFactory(seed: number = 42): SeedFactory {
  // Deterministic pseudo-random using seed
  const seededRandom = (min: number, max: number) => {
    const x = Math.sin(seed * 9301 + 49297) % 233280;
    const r = (x + 233280) / 233280;
    return Math.floor(r * (max - min + 1)) + min;
  };

  const factory: SeedFactory = {
    factoryId: `TEST-FACTORY-${seed}`,
    factoryName: `Paper Cup Works ${seed}`,
    ownerPhone: `9876543${String(seed).padStart(3, '0')}`,
    email: `test${seed}@munshiai.co.in`,
    password: 'Test@123456',
    address: '123 Industrial Area, Mumbai, Maharashtra - 400001',
    gstin: `27AADCB${seededRandom(1000, 9999)}FZY${seededRandom(1, 9)}Z`,

    masterData: {
      products: [
        { name: 'Paper Cup', size: '100ML', variety: 'Plain' },
        { name: 'Paper Cup', size: '150ML', variety: 'Printed' },
        { name: 'Paper Glass', size: '200ML', variety: 'Plain' },
      ],
      rawMaterials: [
        { name: 'Paper Roll', unit: 'KG' },
        { name: 'Plastic Lid', unit: 'PCS' },
        { name: 'Ink', unit: 'LTR' },
      ],
      machines: [
        { name: 'Cup Making Machine A', type: 'CUP_MAKER' },
        { name: 'Printing Machine', type: 'PRINTER' },
      ],
      workers: [
        { name: 'Ramesh Kumar', phone: '9876543210', wage: 15000 },
        { name: 'Suresh Yadav', phone: '9876543211', wage: 12000 },
        { name: 'Mahesh Patel', phone: '9876543212', wage: 10000 },
      ],
    },

    inventory: [
      { material: 'Paper Roll', quantity: 500, unitCost: 85 },
      { material: 'Plastic Lid', quantity: 10000, unitCost: 0.5 },
      { material: 'Ink', quantity: 20, unitCost: 450 },
    ],

    production: Array.from({ length: 7 }, (_, i) => ({
      day: i + 1,
      product: ['Paper Cup 100ML Plain', 'Paper Cup 150ML Printed', 'Paper Glass 200ML Plain'][i % 3],
      quantity: seededRandom(5000, 15000),
      wastage: Math.round(seededRandom(50, 200) / 10) / 10,
    })),

    sales: [
      {
        customer: 'ABC Enterprises',
        product: 'Paper Cup 100ML Plain',
        quantity: 5000,
        rate: 0.85,
      },
      {
        customer: 'XYZ Traders',
        product: 'Paper Cup 150ML Printed',
        quantity: 3000,
        rate: 1.25,
      },
    ],
  };

  return factory;
}

export const ASSERTIONS = {
  NO_500: 'No 500 Internal Server Error',
  NO_502: 'No 502 Bad Gateway',
  NO_CONSOLE_CRASH: 'No frontend console errors',
  INVENTORY_MATH: 'Inventory math is correct',
  OUTSTANDING_MATH: 'Outstanding calculation is correct',
  INVOICE_GENERATED: 'Invoice PDF generated successfully',
  RECOVERY_SUGGESTION: 'Recovery suggestion generated',
  BRIEFING_SAVED: 'Daily briefing snapshot saved',
  ROLE_MASKING: 'Sub Owner role masking works',
};
