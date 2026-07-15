(function initHydroGeometryMath(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.OpenFastHydroGeometryMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function hydroGeometryFactory() {
  'use strict';

  const EPSILON = 1e-8;

  function numberOrNull(value) {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function flag(value) {
    return value === true || value === 1 || ['true', 't', '1', '.true.'].includes(String(value).trim().toLowerCase());
  }

  function vector(x = 0, y = 0, z = 0) {
    return [x, y, z];
  }

  function add(a, b) {
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  }

  function subtract(a, b) {
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  }

  function multiply(a, scalar) {
    return [a[0] * scalar, a[1] * scalar, a[2] * scalar];
  }

  function dot(a, b) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  }

  function cross(a, b) {
    return [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0]
    ];
  }

  function magnitude(a) {
    return Math.hypot(a[0], a[1], a[2]);
  }

  function normalize(a) {
    const length = magnitude(a);
    return length > EPSILON ? multiply(a, 1 / length) : null;
  }

  function rotateAroundAxis(value, axis, angleRadians) {
    const cosine = Math.cos(angleRadians);
    const sine = Math.sin(angleRadians);
    return add(
      add(multiply(value, cosine), multiply(cross(axis, value), sine)),
      multiply(axis, dot(axis, value) * (1 - cosine))
    );
  }

  function memberFrame(start, end, spinDegrees = 0) {
    const axis = normalize(subtract(end, start));
    if (!axis) return null;
    let sideA = Math.abs(axis[2]) > 1 - 1e-7 ? vector(1, 0, 0) : normalize(cross(vector(0, 0, 1), axis));
    if (!sideA) sideA = vector(1, 0, 0);
    const angle = (numberOrNull(spinDegrees) || 0) * Math.PI / 180;
    sideA = normalize(rotateAroundAxis(sideA, axis, angle));
    const sideB = normalize(cross(axis, sideA));
    return { axis, sideA, sideB };
  }

  function issue(severity, code, objectType, objectId, field, messageZh, messageEn) {
    return { severity, code, objectType, objectId, field, messageZh, messageEn };
  }

  function idValue(row, key) {
    const id = numberOrNull(row?.[key]);
    return id === null ? null : Math.trunc(id);
  }

  function rowsById(rows, key, issues, objectType) {
    const map = new Map();
    for (const row of Array.isArray(rows) ? rows : []) {
      const id = idValue(row, key);
      if (id === null) {
        issues.push(issue('error', 'invalid_id', objectType, null, key,
          `${objectType} 的 ${key} 必须是有效整数。`, `${objectType} ${key} must be a valid integer.`));
        continue;
      }
      if (map.has(id)) {
        issues.push(issue('error', 'duplicate_id', objectType, id, key,
          `${objectType} ${id} 重复。`, `${objectType} ${id} is duplicated.`));
        continue;
      }
      map.set(id, row);
    }
    return map;
  }

  function issueForObject(issues, objectType, objectId) {
    return issues.filter(item => item.objectType === objectType && Number(item.objectId) === Number(objectId));
  }

  function sectionValues(row, rectangular) {
    if (!row) return null;
    if (rectangular) {
      return {
        shape: 'rectangle',
        a: numberOrNull(row.PropA),
        b: numberOrNull(row.PropB),
        thickness: numberOrNull(row.PropThck)
      };
    }
    return {
      shape: 'cylinder',
      diameter: numberOrNull(row.PropD),
      thickness: numberOrNull(row.PropThck)
    };
  }

  function validateSection(section, memberId, endpoint, rectangular, issues) {
    if (!section) return;
    if (rectangular) {
      if (!(section.a > 0)) {
        issues.push(issue('error', 'invalid_section_size', 'member', memberId, `PropA${endpoint}`,
          `Member ${memberId} 的${endpoint === 1 ? '起点' : '终点'}矩形边长 PropA 必须大于 0。`,
          `Member ${memberId} endpoint ${endpoint} PropA must be greater than 0.`));
      }
      if (!(section.b > 0)) {
        issues.push(issue('error', 'invalid_section_size', 'member', memberId, `PropB${endpoint}`,
          `Member ${memberId} 的${endpoint === 1 ? '起点' : '终点'}矩形边长 PropB 必须大于 0。`,
          `Member ${memberId} endpoint ${endpoint} PropB must be greater than 0.`));
      }
      if (section.thickness === null || section.thickness < 0 || section.thickness > Math.min(section.a || 0, section.b || 0) / 2) {
        issues.push(issue('error', 'invalid_section_thickness', 'member', memberId, `PropThck${endpoint}`,
          `Member ${memberId} 的${endpoint === 1 ? '起点' : '终点'}矩形壁厚无效。`,
          `Member ${memberId} endpoint ${endpoint} rectangular wall thickness is invalid.`));
      }
    } else {
      if (!(section.diameter > 0)) {
        issues.push(issue('error', 'invalid_section_size', 'member', memberId, `PropD${endpoint}`,
          `Member ${memberId} 的${endpoint === 1 ? '起点' : '终点'}直径 PropD 必须大于 0。`,
          `Member ${memberId} endpoint ${endpoint} PropD must be greater than 0.`));
      }
      if (section.thickness === null || section.thickness < 0 || section.thickness > (section.diameter || 0) / 2) {
        issues.push(issue('error', 'invalid_section_thickness', 'member', memberId, `PropThck${endpoint}`,
          `Member ${memberId} 的${endpoint === 1 ? '起点' : '终点'}圆柱壁厚无效。`,
          `Member ${memberId} endpoint ${endpoint} cylindrical wall thickness is invalid.`));
      }
    }
  }

  function diagnoseHydroTables(tables = {}, options = {}) {
    const issues = [];
    const members = Array.isArray(tables.members) ? tables.members : [];
    const joints = Array.isArray(tables.joints) ? tables.joints : [];
    const target = String(options.targetFormat || 'v5').toLowerCase();
    const v4Target = ['auto_v4_runtime', 'v4', 'legacy_v4'].includes(target);
    const jointMap = rowsById(joints, 'JointID', issues, 'joint');
    const cylPropMap = rowsById(tables.prop_sets_cyl, 'PropSetID', issues, 'cylindrical property');
    const recPropMap = rowsById(tables.prop_sets_rec, 'MPropSetID', issues, 'rectangular property');
    const memberMap = rowsById(members, 'MemberID', issues, 'member');
    const cylCoeffMap = rowsById(tables.member_coeffs_cyl, 'MemberID', issues, 'cylindrical coefficient');
    const recCoeffMap = rowsById(tables.member_coeffs_rec, 'MemberID', issues, 'rectangular coefficient');
    const usedJoints = new Set();
    const usedCylProps = new Set();
    const usedRecProps = new Set();

    for (const [jointId, row] of jointMap) {
      for (const field of ['Jointxi', 'Jointyi', 'Jointzi']) {
        if (numberOrNull(row[field]) === null) {
          issues.push(issue('error', 'invalid_coordinate', 'joint', jointId, field,
            `Joint ${jointId} 的 ${field} 不是有效坐标。`, `Joint ${jointId} ${field} is not a valid coordinate.`));
        }
      }
    }

    if (v4Target && ((tables.prop_sets_rec || []).length || (tables.depth_rec || []).length || (tables.member_coeffs_rec || []).length)) {
      issues.push(issue('error', 'rectangular_table_in_v4', 'hydrodyn', null, 'target_format',
        '当前 HydroDyn v4 上下文不能写入矩形构件表。', 'The current HydroDyn v4 context cannot write rectangular-member tables.'));
    }

    for (const [memberId, row] of memberMap) {
      const rectangular = Number(row.MSecGeom || 1) === 2;
      const startJointId = idValue(row, 'MJointID1');
      const endJointId = idValue(row, 'MJointID2');
      const startPropId = idValue(row, 'MPropSetID1');
      const endPropId = idValue(row, 'MPropSetID2');
      const propertyMap = rectangular ? recPropMap : cylPropMap;
      const coefficientMap = rectangular ? recCoeffMap : cylCoeffMap;

      if (rectangular && v4Target) {
        issues.push(issue('error', 'rectangle_requires_v5', 'member', memberId, 'MSecGeom',
          `Member ${memberId} 是矩形构件，必须使用原生 HydroDyn v5。`,
          `Member ${memberId} is rectangular and requires native HydroDyn v5.`));
      }
      if (startJointId !== null) usedJoints.add(startJointId);
      if (endJointId !== null) usedJoints.add(endJointId);
      if (rectangular) {
        if (startPropId !== null) usedRecProps.add(startPropId);
        if (endPropId !== null) usedRecProps.add(endPropId);
      } else {
        if (startPropId !== null) usedCylProps.add(startPropId);
        if (endPropId !== null) usedCylProps.add(endPropId);
      }

      const startJoint = jointMap.get(startJointId);
      const endJoint = jointMap.get(endJointId);
      if (!startJoint) {
        issues.push(issue('error', 'missing_joint', 'member', memberId, 'MJointID1',
          `Member ${memberId} 缺少起点 Joint ${row.MJointID1}。`, `Member ${memberId} is missing start Joint ${row.MJointID1}.`));
      }
      if (!endJoint) {
        issues.push(issue('error', 'missing_joint', 'member', memberId, 'MJointID2',
          `Member ${memberId} 缺少终点 Joint ${row.MJointID2}。`, `Member ${memberId} is missing end Joint ${row.MJointID2}.`));
      }
      if (startJointId !== null && startJointId === endJointId) {
        issues.push(issue('error', 'same_endpoint_joint', 'member', memberId, 'MJointID2',
          `Member ${memberId} 的起点和终点不能引用同一节点。`,
          `Member ${memberId} cannot use the same joint at both endpoints.`));
      }

      const startPoint = startJoint ? [numberOrNull(startJoint.Jointxi), numberOrNull(startJoint.Jointyi), numberOrNull(startJoint.Jointzi)] : null;
      const endPoint = endJoint ? [numberOrNull(endJoint.Jointxi), numberOrNull(endJoint.Jointyi), numberOrNull(endJoint.Jointzi)] : null;
      if (startPoint?.every(value => value !== null) && endPoint?.every(value => value !== null) && magnitude(subtract(endPoint, startPoint)) <= EPSILON) {
        issues.push(issue('error', 'zero_length_member', 'member', memberId, 'MJointID2',
          `Member ${memberId} 的空间长度为 0。`, `Member ${memberId} has zero spatial length.`));
      }

      const startProperty = propertyMap.get(startPropId);
      const endProperty = propertyMap.get(endPropId);
      if (!startProperty) {
        issues.push(issue('error', 'missing_property', 'member', memberId, 'MPropSetID1',
          `Member ${memberId} 缺少起点截面 Property ${row.MPropSetID1}。`,
          `Member ${memberId} is missing start Property ${row.MPropSetID1}.`));
      }
      if (!endProperty) {
        issues.push(issue('error', 'missing_property', 'member', memberId, 'MPropSetID2',
          `Member ${memberId} 缺少终点截面 Property ${row.MPropSetID2}。`,
          `Member ${memberId} is missing end Property ${row.MPropSetID2}.`));
      }
      validateSection(sectionValues(startProperty, rectangular), memberId, 1, rectangular, issues);
      validateSection(sectionValues(endProperty, rectangular), memberId, 2, rectangular, issues);

      const divisionSize = numberOrNull(row.MDivSize);
      if (!(divisionSize > 0)) {
        issues.push(issue('error', 'invalid_division_size', 'member', memberId, 'MDivSize',
          `Member ${memberId} 的 MDivSize 必须大于 0。`, `Member ${memberId} MDivSize must be greater than 0.`));
      }
      if (Number(row.MCoefMod || 1) === 3 && !coefficientMap.has(memberId)) {
        issues.push(issue('error', 'missing_member_coefficients', 'member', memberId, 'MCoefMod',
          `Member ${memberId} 使用独立系数，但缺少对应系数行。`,
          `Member ${memberId} uses member-specific coefficients but has no coefficient row.`));
      }

      if (v4Target && Number(row.MHstLMod || 0) === 1 && !flag(row.PropPot) && !rectangular && startJoint && endJoint) {
        const nearWater = [[startJoint, startProperty], [endJoint, endProperty]].some(([joint, property]) => {
          const z = numberOrNull(joint?.Jointzi);
          const diameter = numberOrNull(property?.PropD);
          return z !== null && diameter !== null && Math.abs(z) < Math.abs(diameter) / 2;
        });
        if (nearWater) {
          issues.push(issue('error', 'v4_hydrostatic_endplate_at_waterline', 'member', memberId, 'MHstLMod',
            `Member ${memberId} 的解析静水力端板过于接近水面；请使用 MHstLMod=0 或调整端点。`,
            `Member ${memberId} analytical hydrostatic endplate is too close to the waterline; use MHstLMod=0 or move the endpoint.`));
        }
      }
    }

    if (members.length) {
      for (const jointId of jointMap.keys()) {
        if (!usedJoints.has(jointId)) {
          issues.push(issue('warning', 'orphan_joint', 'joint', jointId, 'JointID',
            `Joint ${jointId} 未被任何构件引用。`, `Joint ${jointId} is not referenced by any member.`));
        }
      }
      for (const propId of cylPropMap.keys()) {
        if (!usedCylProps.has(propId)) {
          issues.push(issue('warning', 'orphan_property', 'cylindrical property', propId, 'PropSetID',
            `圆柱截面 Property ${propId} 未被任何构件引用。`,
            `Cylindrical Property ${propId} is not referenced by any member.`));
        }
      }
      for (const propId of recPropMap.keys()) {
        if (!usedRecProps.has(propId)) {
          issues.push(issue('warning', 'orphan_property', 'rectangular property', propId, 'MPropSetID',
            `矩形截面 Property ${propId} 未被任何构件引用。`,
            `Rectangular Property ${propId} is not referenced by any member.`));
        }
      }
    }
    for (const coeffId of cylCoeffMap.keys()) {
      if (memberMap.size && !memberMap.has(coeffId)) {
        issues.push(issue('warning', 'orphan_coefficient', 'cylindrical coefficient', coeffId, 'MemberID',
          `圆柱系数 ${coeffId} 没有对应构件。`, `Cylindrical coefficient ${coeffId} has no matching member.`));
      }
    }
    for (const coeffId of recCoeffMap.keys()) {
      if (memberMap.size && !memberMap.has(coeffId)) {
        issues.push(issue('warning', 'orphan_coefficient', 'rectangular coefficient', coeffId, 'MemberID',
          `矩形系数 ${coeffId} 没有对应构件。`, `Rectangular coefficient ${coeffId} has no matching member.`));
      }
    }
    return issues;
  }

  function pointFromJoint(row) {
    const point = [numberOrNull(row?.Jointxi), numberOrNull(row?.Jointyi), numberOrNull(row?.Jointzi)];
    return point.every(value => value !== null) ? point : null;
  }

  function buildHydroGeometry(tables = {}, options = {}) {
    const issues = diagnoseHydroTables(tables, options);
    const jointMap = new Map((tables.joints || []).map(row => [idValue(row, 'JointID'), row]).filter(([id]) => id !== null));
    const cylPropMap = new Map((tables.prop_sets_cyl || []).map(row => [idValue(row, 'PropSetID'), row]).filter(([id]) => id !== null));
    const recPropMap = new Map((tables.prop_sets_rec || []).map(row => [idValue(row, 'MPropSetID'), row]).filter(([id]) => id !== null));
    const usedJoints = new Set((tables.members || []).flatMap(row => [idValue(row, 'MJointID1'), idValue(row, 'MJointID2')]));
    const joints = [];
    const members = [];
    const bounds = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
    const includePoint = point => {
      for (let index = 0; index < 3; index += 1) {
        bounds.min[index] = Math.min(bounds.min[index], point[index]);
        bounds.max[index] = Math.max(bounds.max[index], point[index]);
      }
    };

    for (const [jointId, row] of jointMap) {
      const position = pointFromJoint(row);
      if (!position) continue;
      includePoint(position);
      joints.push({
        id: jointId,
        position,
        orphan: !usedJoints.has(jointId),
        issues: issueForObject(issues, 'joint', jointId),
        referencedMemberIds: (tables.members || [])
          .filter(member => [idValue(member, 'MJointID1'), idValue(member, 'MJointID2')].includes(jointId))
          .map(member => idValue(member, 'MemberID'))
          .filter(id => id !== null)
      });
    }

    const maxDivisionMarkers = Math.max(0, Number(options.maxDivisionMarkers ?? 2000));
    for (const row of tables.members || []) {
      const id = idValue(row, 'MemberID');
      if (id === null) continue;
      const startJointId = idValue(row, 'MJointID1');
      const endJointId = idValue(row, 'MJointID2');
      const start = pointFromJoint(jointMap.get(startJointId));
      const end = pointFromJoint(jointMap.get(endJointId));
      const rectangular = Number(row.MSecGeom || 1) === 2;
      const propertyMap = rectangular ? recPropMap : cylPropMap;
      const sectionStart = sectionValues(propertyMap.get(idValue(row, 'MPropSetID1')), rectangular);
      const sectionEnd = sectionValues(propertyMap.get(idValue(row, 'MPropSetID2')), rectangular);
      const length = start && end ? magnitude(subtract(end, start)) : null;
      const frame = start && end ? memberFrame(start, end, row.MSpinOrient) : null;
      const divisionSize = numberOrNull(row.MDivSize);
      const divisionCount = length !== null && length > EPSILON && divisionSize > 0 ? Math.ceil(length / divisionSize) : 0;
      const internalPoints = [];
      if (start && end && divisionCount > 1) {
        const markers = Math.min(divisionCount - 1, maxDivisionMarkers);
        for (let index = 1; index <= markers; index += 1) {
          const fraction = divisionCount - 1 > maxDivisionMarkers
            ? index / (markers + 1)
            : index / divisionCount;
          internalPoints.push(add(start, multiply(subtract(end, start), fraction)));
        }
      }
      members.push({
        id,
        startJointId,
        endJointId,
        start,
        end,
        length,
        frame,
        shape: rectangular ? 'rectangle' : 'cylinder',
        sectionStart,
        sectionEnd,
        spinDegrees: numberOrNull(row.MSpinOrient) || 0,
        divisionSize,
        divisionCount,
        internalPoints,
        divisionPreviewLimited: divisionCount - 1 > maxDivisionMarkers,
        propPot: flag(row.PropPot),
        coefficientMode: numberOrNull(row.MCoefMod),
        hydrostaticMode: numberOrNull(row.MHstLMod),
        issues: issueForObject(issues, 'member', id)
      });
    }

    if (!Number.isFinite(bounds.min[0])) {
      bounds.min = [-1, -1, -1];
      bounds.max = [1, 1, 1];
    }
    return { joints, members, issues, bounds };
  }

  return {
    EPSILON,
    numberOrNull,
    flag,
    memberFrame,
    diagnoseHydroTables,
    buildHydroGeometry
  };
});
