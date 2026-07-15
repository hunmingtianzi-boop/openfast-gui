const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildHydroGeometry,
  diagnoseHydroTables,
  memberFrame
} = require('./hydro_geometry.js');
const umaineYScenario = require('../scenarios/iea_15_240_umaine_y_morison_rectangular.json');

function baseTables() {
  return {
    joints: [
      { JointID: 1, Jointxi: -59.4, Jointyi: 0, Jointzi: -20 },
      { JointID: 2, Jointxi: -59.4, Jointyi: 0, Jointzi: 2 },
      { JointID: 3, Jointxi: 29.1, Jointyi: 51.5, Jointzi: -20 },
      { JointID: 4, Jointxi: 29.1, Jointyi: 51.5, Jointzi: 2 },
      { JointID: 5, Jointxi: 29.8, Jointyi: -51.5, Jointzi: -20 },
      { JointID: 6, Jointxi: 29.8, Jointyi: -51.5, Jointzi: 2 }
    ],
    prop_sets_cyl: [{ PropSetID: 1, PropD: 12, PropThck: 0.05 }],
    prop_sets_rec: [{ MPropSetID: 2, PropA: 8, PropB: 5, PropThck: 0.05 }],
    member_coeffs_cyl: [1, 2, 3].map(MemberID => ({ MemberID })),
    member_coeffs_rec: [],
    members: [
      { MemberID: 1, MJointID1: 1, MJointID2: 2, MPropSetID1: 1, MPropSetID2: 1, MSecGeom: 1, MDivSize: 0.5, MCoefMod: 3, PropPot: true },
      { MemberID: 2, MJointID1: 3, MJointID2: 4, MPropSetID1: 1, MPropSetID2: 1, MSecGeom: 1, MDivSize: 0.5, MCoefMod: 3, PropPot: true },
      { MemberID: 3, MJointID1: 5, MJointID2: 6, MPropSetID1: 1, MPropSetID2: 1, MSecGeom: 1, MDivSize: 0.5, MCoefMod: 3, PropPot: true }
    ]
  };
}

function close(actual, expected, tolerance = 1e-9) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} is not close to ${expected}`);
}

test('IEA 15MW three-column layout preserves XY coordinates and Z extents', () => {
  const geometry = buildHydroGeometry(baseTables(), { targetFormat: 'v5' });
  assert.equal(geometry.members.length, 3);
  assert.deepEqual(geometry.members.map(member => member.start.slice(0, 2)), [
    [-59.4, 0], [29.1, 51.5], [29.8, -51.5]
  ]);
  assert.deepEqual(geometry.bounds.min, [-59.4, -51.5, -20]);
  assert.deepEqual(geometry.bounds.max, [29.8, 51.5, 2]);
  assert.equal(geometry.issues.filter(item => item.severity === 'error').length, 0);
});

test('official UMaineSemi scenario forms a connected Y with rectangular pontoons', () => {
  const tables = (umaineYScenario.hydrodyn_tables || umaineYScenario.cases[0].hydrodyn_tables).tables;
  const geometry = buildHydroGeometry(tables, { targetFormat: 'v5' });
  const rectangular = geometry.members.filter(member => member.shape === 'rectangle');

  assert.equal(geometry.members.length, 18);
  assert.equal(rectangular.length, 3);
  assert.deepEqual(rectangular.map(member => [member.sectionStart.a, member.sectionStart.b]), [
    [12.5, 7], [12.5, 7], [12.5, 7]
  ]);
  assert.deepEqual(rectangular.map(member => member.start), [
    [0, 0, -16.5], [0, 0, -16.5], [0, 0, -16.5]
  ]);
  assert.deepEqual(rectangular.map(member => member.end.slice(0, 2)), [
    [-51.75, 0], [25.875, 44.816815743], [25.875, -44.816815743]
  ]);
  assert.deepEqual(geometry.bounds.min, [-51.75, -44.816815743, -20]);
  assert.deepEqual(geometry.bounds.max, [25.875, 44.816815743, 15]);
  assert.equal(geometry.issues.filter(item => item.severity === 'error').length, 0);
});

test('IEA 15MW report monopile preserves the official wetted geometry', () => {
  const tables = baseTables();
  tables.joints = [
    { JointID: 1, Jointxi: 0, Jointyi: 0, Jointzi: -30.1, JointAxID: 1, JointOvrlp: 0 },
    { JointID: 2, Jointxi: 0, Jointyi: 0, Jointzi: 15, JointAxID: 1, JointOvrlp: 0 }
  ];
  tables.prop_sets_cyl = [{ PropSetID: 1, PropD: 10, PropThck: 0.055341 }];
  tables.prop_sets_rec = [];
  tables.member_coeffs_cyl = [];
  tables.member_coeffs_rec = [];
  tables.members = [{
    MemberID: 1,
    MJointID1: 1,
    MJointID2: 2,
    MPropSetID1: 1,
    MPropSetID2: 1,
    MDivSize: 0.5,
    MCoefMod: 1,
    PropPot: false
  }];

  const geometry = buildHydroGeometry(tables, { targetFormat: 'v4' });
  assert.equal(geometry.members.length, 1);
  assert.equal(geometry.members[0].length, 45.1);
  assert.equal(geometry.members[0].sectionStart.diameter, 10);
  assert.equal(geometry.members[0].sectionStart.thickness, 0.055341);
  assert.equal(geometry.members[0].divisionCount, 91);
  assert.deepEqual(geometry.bounds.min, [0, 0, -30.1]);
  assert.deepEqual(geometry.bounds.max, [0, 0, 15]);
  assert.equal(geometry.issues.filter(item => item.severity === 'error').length, 0);
});

test('shared joint edits update every referencing member', () => {
  const tables = baseTables();
  tables.members[1].MJointID1 = 2;
  tables.joints[1].Jointxi = -42;
  const geometry = buildHydroGeometry(tables, { targetFormat: 'v5' });
  assert.deepEqual(geometry.members[0].end, [-42, 0, 2]);
  assert.deepEqual(geometry.members[1].start, [-42, 0, 2]);
});

test('cylindrical and rectangular endpoint sections preserve taper dimensions', () => {
  const tables = baseTables();
  tables.prop_sets_cyl.push({ PropSetID: 3, PropD: 8, PropThck: 0.04 });
  tables.members[0].MPropSetID2 = 3;
  tables.members[1].MSecGeom = 2;
  tables.members[1].MPropSetID1 = 2;
  tables.members[1].MPropSetID2 = 2;
  tables.member_coeffs_cyl = tables.member_coeffs_cyl.filter(row => row.MemberID !== 2);
  tables.member_coeffs_rec = [{ MemberID: 2 }];
  const geometry = buildHydroGeometry(tables, { targetFormat: 'v5' });
  assert.equal(geometry.members[0].sectionStart.diameter, 12);
  assert.equal(geometry.members[0].sectionEnd.diameter, 8);
  assert.equal(geometry.members[1].sectionStart.a, 8);
  assert.equal(geometry.members[1].sectionEnd.b, 5);
});

test('vertical rectangular member follows HydroDyn right-hand spin convention', () => {
  const zero = memberFrame([0, 0, -10], [0, 0, 10], 0);
  assert.deepEqual(zero.sideA.map(value => Math.round(value)), [1, 0, 0]);
  assert.deepEqual(zero.sideB.map(value => Math.round(value)), [0, 1, 0]);

  const positive = memberFrame([0, 0, -10], [0, 0, 10], 90);
  close(positive.sideA[0], 0);
  close(positive.sideA[1], 1);
  close(positive.sideA[2], 0);

  const negative = memberFrame([0, 0, -10], [0, 0, 10], -90);
  close(negative.sideA[0], 0);
  close(negative.sideA[1], -1);
  close(negative.sideA[2], 0);
});

test('inclined member keeps Side A horizontal at zero spin', () => {
  const frame = memberFrame([0, 0, 0], [4, 3, 5], 0);
  close(frame.sideA[2], 0);
  close(frame.axis[0] * frame.sideA[0] + frame.axis[1] * frame.sideA[1] + frame.axis[2] * frame.sideA[2], 0);
});

test('MDivSize preview uses ceil(length / MDivSize)', () => {
  const tables = baseTables();
  tables.members = [tables.members[0]];
  tables.member_coeffs_cyl = [{ MemberID: 1 }];
  const geometry = buildHydroGeometry(tables, { targetFormat: 'v5' });
  assert.equal(geometry.members[0].length, 22);
  assert.equal(geometry.members[0].divisionCount, 44);
  assert.equal(geometry.members[0].internalPoints.length, 43);
});

test('diagnostics report zero length, missing references and invalid coordinates', () => {
  const tables = baseTables();
  tables.joints[0].Jointxi = 'not-a-number';
  tables.members[0].MJointID2 = 999;
  tables.members[1].MJointID2 = tables.members[1].MJointID1;
  const issues = diagnoseHydroTables(tables, { targetFormat: 'v5' });
  const codes = new Set(issues.map(item => item.code));
  assert.ok(codes.has('invalid_coordinate'));
  assert.ok(codes.has('missing_joint'));
  assert.ok(codes.has('same_endpoint_joint'));
});

test('v4 diagnostics reject rectangular members', () => {
  const tables = baseTables();
  tables.members[0].MSecGeom = 2;
  tables.members[0].MPropSetID1 = 2;
  tables.members[0].MPropSetID2 = 2;
  tables.member_coeffs_rec = [{ MemberID: 1 }];
  const issues = diagnoseHydroTables(tables, { targetFormat: 'v4' });
  assert.ok(issues.some(item => item.code === 'rectangle_requires_v5' && item.objectId === 1));
});
