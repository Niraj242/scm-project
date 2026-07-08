import React, { useState, useEffect } from 'react';
import './Afterchannel.css';
 
const API = 'https://scm-backend-pshv.onrender.com';
 
const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [], autopackaging: [], fps: [] });
  
  const [moNumber, setMoNumber] = useState('');
  const [selectedVariant, setSelectedVariant] = useState('');
  const [actualProductionQty, setActualProductionQty] = useState(0);
  
  const [editingRecord, setEditingRecord] = useState(null);
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState('');
 
  const [formDate, setFormDate] = useState('');
 
  const [bearingFamily, setBearingFamily] = useState(''); 
 
  const [irScrapVal, setIrScrapVal] = useState('');
  const [orScrapVal, setOrScrapVal] = useState('');
  const [cageScrapVal, setCageScrapVal] = useState('');
  const [ballScrapVal, setBallScrapVal] = useState('');
  const [rollerScrapVal, setRollerScrapVal] = useState('');
  const [remarkVal, setRemarkVal] = useState('');
  
  const [irSentVal, setIrSentVal] = useState('');
  const [irStationVal, setIrStationVal] = useState('');
  const [orSentVal, setOrSentVal] = useState('');
  const [orStationVal, setOrStationVal] = useState('');
  const [cageSentVal, setCageSentVal] = useState('');
  const [cageStationVal, setCageStationVal] = useState('');
  const [rollerSentVal, setRollerSentVal] = useState('');
  const [rollerStationVal, setRollerStationVal] = useState('');
 
  const [expandedMOs, setExpandedMOs] = useState({});
  const [expandedVariants, setExpandedVariants] = useState({});
 
  // P-VSM Flow States
  const [pvsmMo, setPvsmMo] = useState('');
  const [pvsmType, setPvsmType] = useState('');
  const [isFlowLoaded, setIsFlowLoaded] = useState(false);

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
  }, []);
 
  const fetchMasterData = async () => {
    try {
      const res = await fetch(`${API}/api/mo-lookup`);
      const data = await res.json();
      if (data.status === 'success') {
        setMoCache(data.data || {});
      }
    } catch (err) {
      console.error("Master Reference Load Failure:", err);
    }
  };
 
  const fetchLedgers = async () => {
    try {
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`);
      const json = await res.json();
      if (json.status === 'success' || json.data) {
        setLedgers({
          accurate: json.data?.accurate || [],
          cps: json.data?.cps || [],
          rework: json.data?.rework || [],
          dismantling: json.data?.dismantling || json.data?.vibration || [],
          autopackaging: json.data?.autopackaging || [],
          fps: json.data?.fps || []
        });
      }
    } catch (err) {
      console.error("Ledger Sync Failure:", err);
    }
  };
 
  const getQtyFromRow = (row) => {
    for (const key in row) {
      const cleanKey = key.toLowerCase().replace(/[^a-z]/g, '');
      if (['qty', 'quantity', 'production', 'target', 'plan', 'total'].some(w => cleanKey.includes(w))) {
        const val = parseFloat(String(row[key]).replace(/,/g, ''));
        if (!isNaN(val) && val > 0) return val;
      }
    }
    return 0;
  };
 
  const getTypeFromRow = (row) => {
    for (const key in row) {
      const cleanKey = key.toLowerCase().replace(/[^a-z]/g, '');
      if (['type', 'variant', 'model', 'bearing', 'item'].some(w => cleanKey.includes(w))) {
        return String(row[key]).trim();
      }
    }
    return 'UNKNOWN_VARIANT'; 
  };
 
  const calculateProduction = (rawRows, variantToMatch) => {
    if (!rawRows || !Array.isArray(rawRows)) return 0;
    const cleanMatch = String(variantToMatch || '').trim().toUpperCase();
    return rawRows.reduce((sum, r) => {
      const rowType = getTypeFromRow(r).toUpperCase();
      if (rowType === cleanMatch) return sum + getQtyFromRow(r);
      return sum;
    }, 0);
  };
 
  const allUniqueVariants = [...new Set(Object.values(moCache).flatMap(rows => rows.map(r => getTypeFromRow(r))))].filter(Boolean);
  const allUniqueMos = Object.keys(moCache);
 
  const dynamicVariantsList = moNumber.trim() && moCache[moNumber.trim().toUpperCase()]
    ? [...new Set(moCache[moNumber.trim().toUpperCase()].map(r => getTypeFromRow(r)))].filter(Boolean)
    : allUniqueVariants;
 
  const dynamicMosList = selectedVariant.trim()
    ? allUniqueMos.filter(mo => moCache[mo].some(r => getTypeFromRow(r).toUpperCase() === selectedVariant.trim().toUpperCase()))
    : allUniqueMos;
 
  const handleMoBlur = () => {
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      const rawRows = moCache[key];
      const uniqueVariants = [...new Set(rawRows.map(r => getTypeFromRow(r)))].filter(Boolean);
      if (uniqueVariants.length === 1) {
        const vType = uniqueVariants[0];
        setSelectedVariant(vType);
        setActualProductionQty(calculateProduction(rawRows, vType));
      }
    }
  };
 
  const handleVariantChange = (e) => {
    const variantName = e.target.value.toUpperCase();
    setSelectedVariant(variantName);
    if (moNumber && moCache[moNumber.toUpperCase()]) {
      setActualProductionQty(calculateProduction(moCache[moNumber.toUpperCase()], variantName));
    }
  };
 
  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    
    const payload = {
      id: editingRecord ? editingRecord.id : undefined,
      mo: moNumber.toUpperCase(),
      bearing_type: selectedVariant.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      bearingFamily: bearingFamily || null
    };
 
    const numFields = [
      'qtyIn', 'qtySent', 'qty_in', 'qty_sent', 
      'ballScrap', 'rollerScrap', 'cageScrap', 'irScrap', 'orScrap',
      'irSent', 'orSent', 'cageSent', 'rollerSent'
    ];
 
    for (let [key, value] of fd.entries()) {
      let finalValue = value;
      if (numFields.includes(key)) {
        finalValue = (value !== '' && !isNaN(Number(value))) ? Number(value) : 0;
      } else if (!value || value.trim() === '') {
        finalValue = null;
      }
      payload[key] = finalValue;
      
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
      if (snakeKey !== key) payload[snakeKey] = finalValue;
    }
 
    try {
      const targetEndpoint = endpoint === 'dismantling' ? 'vibration' : endpoint;
      const response = await fetch(`${API}/api/afterchannel/${targetEndpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
      
      alert(editingRecord ? "Entry Updated Successfully!" : "Operational Record Logged Successfully!");
      e.target.reset();
      setEditingRecord(null);
      resetComponentScrapStates();
      await fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };
 
  const resetComponentScrapStates = () => {
    setIrScrapVal(''); setOrScrapVal(''); setCageScrapVal(''); setBallScrapVal(''); setRollerScrapVal(''); setRemarkVal('');
    setIrSentVal(''); setIrStationVal(''); setOrSentVal(''); setOrStationVal('');
    setCageSentVal(''); setCageStationVal(''); setRollerSentVal(''); setRollerStationVal('');
  };
 
  const handleEdit = (record) => {
    setMoNumber(record.mo || '');
    setSelectedVariant(record.type || record.bearing_type || '');
    setBearingFamily(record.bearing_family || record.bearingFamily || '');
    setEntryMode((record.qty_sent || record.qtySent) ? 'OUT' : 'IN');
    
    setIrScrapVal(record.ir_scrap !== undefined && record.ir_scrap !== null ? record.ir_scrap : '');
    setOrScrapVal(record.or_scrap !== undefined && record.or_scrap !== null ? record.or_scrap : '');
    setCageScrapVal(record.cage_scrap !== undefined && record.cage_scrap !== null ? record.cage_scrap : '');
    setBallScrapVal(record.ball_scrap !== undefined && record.ball_scrap !== null ? record.ball_scrap : '');
    setRollerScrapVal(record.roller_scrap !== undefined && record.roller_scrap !== null ? record.roller_scrap : '');
    setRemarkVal(record.remark || '');
    
    setIrSentVal(record.ir_sent ?? ''); setIrStationVal(record.ir_station || '');
    setOrSentVal(record.or_sent ?? ''); setOrStationVal(record.or_station || '');
    setCageSentVal(record.cage_sent ?? ''); setCageStationVal(record.cage_station || '');
    setRollerSentVal(record.roller_sent ?? ''); setRollerStationVal(record.roller_station || '');
 
    setEditingRecord(record);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
 
  const handleDelete = async (id, tab) => {
    if(!window.confirm("Are you sure you want to delete this entry permanently?")) return;
    const endpoint = tab === 'dismantling' ? 'vibration' : tab;
    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}/${id}`, { method: 'DELETE' });
      if(response.ok) {
        await fetchLedgers();
        if(editingRecord && editingRecord.id === id) setEditingRecord(null);
      }
    } catch(err) {
      alert("Delete Error: " + err.message);
    }
  };
 
  const isScrapStation = (val) => String(val || '').trim().toLowerCase().includes('scrap');
 
  const createEmptyFlowObject = () => ({
    accIn: 0, accOut: 0, cpsIn: 0, cpsOut: 0, rwIn: 0, rwOut: 0,
    disIn: 0, disOut: 0, apIn: 0, apOut: 0, fpsIn: 0, 
    irScrap: 0, orScrap: 0, cageScrap: 0, ballScrap: 0, totalScrap: 0, records: [],
    irSentTot: 0, orSentTot: 0, disOutGeneral: 0
  });
 
  const isLoopback = (dept, val) => {
    if (!val) return false;
    const s = String(val).toLowerCase();
    return s.includes('rework') || s.includes('dismantling') || s.includes('vibration') || s.includes(dept);
  };
 
  const addFlowCounts = (node, r) => {
    const dept = r._dept;
    const mFrom = r.material_in_from || r.materialInFrom;
    const nStat = r.next_station || r.nextStation;
 
    if (dept === 'accurate') { 
      if (r.qty_in && !isLoopback('accurate', mFrom)) node.accIn += Number(r.qty_in); 
      if (r.qty_sent && !isLoopback('accurate', nStat)) node.accOut += Number(r.qty_sent); 
    }
    else if (dept === 'cps') { 
      if (r.qty_in && !isLoopback('cps', mFrom)) node.cpsIn += Number(r.qty_in); 
      if (r.qty_sent && !isLoopback('cps', nStat)) node.cpsOut += Number(r.qty_sent); 
    }
    else if (dept === 'autopackaging') { 
      if (r.qty_in && !isLoopback('autopackaging', mFrom)) node.apIn += Number(r.qty_in); 
      if (r.qty_sent && !isLoopback('autopackaging', nStat)) node.apOut += Number(r.qty_sent); 
    }
    else if (dept === 'fps') { 
      if (r.qty_in && !isLoopback('fps', mFrom)) node.fpsIn += Number(r.qty_in); 
    }
    else if (dept === 'rework') { 
      if (r.qty_in) node.rwIn += Number(r.qty_in); 
      if (r.qty_sent) node.rwOut += Number(r.qty_sent); 
    }
    else if (dept === 'dismantling') {
      if (r.qty_in) node.disIn += Number(r.qty_in);
      if (r.qty_sent) node.disOutGeneral += Number(r.qty_sent);
      if (r.ir_sent) node.irSentTot += Number(r.ir_sent);
      if (r.or_sent) node.orSentTot += Number(r.or_sent);
      node.irScrap += (Number(r.ir_scrap) || 0); node.orScrap += (Number(r.or_scrap) || 0);
      node.cageScrap += (Number(r.cage_scrap) || 0); node.ballScrap += (Number(r.ball_scrap) || 0) + (Number(r.roller_scrap) || 0);
      node.totalScrap = node.irScrap + node.orScrap + node.cageScrap + node.ballScrap;
    }
  };
 
  const generateSummaryData = () => {
    const safeLedgers = { accurate: ledgers.accurate||[], cps: ledgers.cps||[], rework: ledgers.rework||[], dismantling: ledgers.dismantling||ledgers.vibration||[], autopackaging: ledgers.autopackaging||[], fps: ledgers.fps||[] };
    const allLists = [
      ...safeLedgers.accurate.map(r=>({...r, _dept:'accurate'})), ...safeLedgers.cps.map(r=>({...r, _dept:'cps'})), 
      ...safeLedgers.rework.map(r=>({...r, _dept:'rework'})), ...safeLedgers.dismantling.map(r=>({...r, _dept:'dismantling'})), 
      ...safeLedgers.autopackaging.map(r=>({...r, _dept:'autopackaging'})), ...safeLedgers.fps.map(r=>({...r, _dept:'fps'}))
    ];
    
    const summaryMap = {};
    allLists.forEach(item => {
      if (!item.mo) return;
      const mo = item.mo.toUpperCase();
      let variant = (item.bearing_type || item.type || item.item_type || '').toUpperCase();
      if (!variant || variant === 'DGBB' || variant === 'TRB') variant = 'FAMILY / OVERALL';
 
      if (!summaryMap[mo]) summaryMap[mo] = { mo, totals: createEmptyFlowObject(), variants: {} };
      if (!summaryMap[mo].variants[variant]) summaryMap[mo].variants[variant] = createEmptyFlowObject();
 
      addFlowCounts(summaryMap[mo].variants[variant], item);
      addFlowCounts(summaryMap[mo].totals, item);
      summaryMap[mo].variants[variant].records.push(item);
    });
 
    Object.values(summaryMap).forEach(moData => {
      moData.totals.disOut = moData.totals.disOutGeneral + Math.min(moData.totals.irSentTot + moData.totals.irScrap, moData.totals.orSentTot + moData.totals.orScrap);
      Object.values(moData.variants).forEach(vData => {
        vData.disOut = vData.disOutGeneral + Math.min(vData.irSentTot + vData.irScrap, vData.orSentTot + vData.orScrap);
      });
    });
 
    let result = Object.values(summaryMap).sort((a, b) => a.mo.localeCompare(b.mo));
    if (ledgerSearchQuery.trim()) result = result.filter(item => item.mo.includes(ledgerSearchQuery.toUpperCase()));
    return result;
  };

  const renderMoDispatchDetails = (records) => {
    // unchanged...
    const outRecs = records.filter(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0);
    if (outRecs.length === 0) return <div className="dispatch-empty-note">No dispatch/scrap events recorded here yet.</div>;
    const grouped = outRecs.reduce((acc, curr) => { if(!acc[curr._dept]) acc[curr._dept] = []; acc[curr._dept].push(curr); return acc; }, {});
 
    return (
      <div className="dispatch-detail-panel">
        {Object.keys(grouped).map(dept => (
          <div key={dept} className="dispatch-dept-card">
            <h4>{dept} Activity</h4>
            <div className="dispatch-events">
              {grouped[dept].map((r, i) => (
                <div key={i} className="dispatch-event">
                  {r.qty_sent > 0 && <div><strong className="qty-highlight">{r.qty_sent}</strong> sent to <strong>{r.next_station || 'N/A'}</strong></div>}
                  {r.ir_sent > 0 && <div><strong className="qty-highlight">{r.ir_sent} IR</strong> sent to <strong>{r.ir_station || 'N/A'}</strong></div>}
                  {r.or_sent > 0 && <div><strong className="qty-highlight">{r.or_sent} OR</strong> sent to <strong>{r.or_station || 'N/A'}</strong></div>}
                  {r.cage_sent > 0 && <div><strong className="qty-highlight">{r.cage_sent} Cage</strong> sent to <strong>{r.cage_station || 'N/A'}</strong></div>}
                  {r.roller_sent > 0 && <div><strong className="qty-highlight">{r.roller_sent} Roller/Ball</strong> sent to <strong>{r.roller_station || 'N/A'}</strong></div>}
                  {(r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0) && (
                      <div className="scrap-line">
                          Scrap: {[r.ir_scrap && `${r.ir_scrap} IR`, r.or_scrap && `${r.or_scrap} OR`, r.cage_scrap && `${r.cage_scrap} Cage`, (r.ball_scrap||r.roller_scrap) && `${r.ball_scrap||r.roller_scrap} Ball/Rollers`].filter(Boolean).join(', ')}
                      </div>
                  )}
                  <span className="meta-line">On: {r.out_date || r.outDate} | Shift: {r.shift_out}</span>
                  {r.remark && <div className="remark-line">"{r.remark}"</div>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };
 
  const renderDepartmentLedger = (deptKey, deptName) => {
    // unchanged...
    const deptData = ledgers[deptKey] || [];
    const records = deptData.filter(l => {
      const search = ledgerSearchQuery.toUpperCase();
      const moMatch = (l.mo || '').toUpperCase().includes(search);
      const typeMatch = (l.bearing_type || l.type || l.item_type || '').toUpperCase().includes(search);
      return moMatch || typeMatch;
    });
 
    if (records.length === 0) return (
      <div className="ledger-empty-card">
        <div className="ledger-empty-header">
          <span className="ledger-empty-title">{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="field-input" style={{width: '300px'}} />
        </div>
        No entries found.
      </div>
    );
 
    return (
      <div className="ledger-card">
        <div className="ledger-card-header">
          <span>{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="ledger-search-input" />
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>MO</th>
                <th>Variant</th>
                <th>Date IN</th>
                <th>Material From</th>
                <th className="col-qty-in">Qty IN</th>
                <th>Date OUT</th>
                <th>Next Station</th>
                <th className="col-qty-out">Qty OUT</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const isScrap = isScrapStation(r.next_station || r.nextStation);
                return (
                  <tr key={i}>
                    <td className="cell-strong">{r.mo || '-'}</td>
                    <td className="cell-strong">{r.bearing_type || r.type || r.item_type || '-'}</td>
                    <td>{r.in_date || r.inDate || '-'}</td>
                    <td>{r.material_in_from || r.materialInFrom || '-'}</td>
                    <td className="cell-qty-in">{r.qty_in || r.qtyIn || '-'}</td>
                    <td>{r.out_date || r.outDate || '-'}</td>
                    <td className={isScrap ? 'cell-scrap-flag' : ''}>
                      {r.next_station || r.nextStation || '-'}
                      {isScrap && <span className="scrap-flag-icon">⚠️</span>}
                    </td>
                    <td className="cell-qty-out">{r.qty_sent || r.qtySent || r.ir_sent || '-'}</td>
                    <td>
                      <button type="button" onClick={() => handleEdit(r)} className="row-action-btn edit-tint" title="Edit">✏️</button>
                      <button type="button" onClick={() => handleDelete(r.id, deptKey)} className="row-action-btn delete-tint" title="Delete">🗑️</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // ================= P-VSM VISUAL FLOW RENDER (EXACT IMAGE REPLICA) =================
  const renderPVSMFlow = () => {
    
    // Filtering Data based on Top Controls
    const getFiltered = (deptKey) => {
        let data = ledgers[deptKey] || [];
        if (isFlowLoaded) {
            if (pvsmMo && pvsmMo !== 'Select MO') {
                data = data.filter(r => (r.mo || '').toUpperCase() === pvsmMo.toUpperCase());
            }
            if (pvsmType && pvsmType !== 'Select Type') {
                data = data.filter(r => (r.bearing_type || r.type || r.item_type || '').toUpperCase() === pvsmType.toUpperCase());
            }
        } else {
            return []; // Show 0s if not loaded
        }
        return data;
    };

    const dataAccurate = getFiltered('accurate');
    const dataCps = getFiltered('cps');
    const dataRework = getFiltered('rework');
    const dataDismantling = getFiltered('dismantling');
    const dataAutopackaging = getFiltered('autopackaging');
    const dataFps = getFiltered('fps');

    // Strict Double Count Prevention Logic
    // Accurate IN: strictly from channel
    const accIn = dataAccurate.reduce((sum, r) => {
        const from = String(r.material_in_from || r.materialInFrom || '').toLowerCase();
        if (!from.includes('rework') && !from.includes('dismantling') && !from.includes('vibration')) {
            return sum + (Number(r.qty_in || r.qtyIn) || 0);
        }
        return sum;
    }, 0);

    // Accurate OUT: strictly forward flow
    const accOut = dataAccurate.reduce((sum, r) => {
        const to = String(r.next_station || r.nextStation || '').toLowerCase();
        if (!to.includes('rework') && !to.includes('dismantling') && !to.includes('vibration')) {
            return sum + (Number(r.qty_sent || r.qtySent) || 0);
        }
        return sum;
    }, 0);

    const sumSimple = (dataList, field1, field2) => dataList.reduce((sum, r) => sum + (Number(r[field1] || r[field2]) || 0), 0);
    
    // Dismantling Specific Scrap
    const dismScrap = dataDismantling.reduce((sum, r) => {
        return sum + (Number(r.ir_scrap)||0) + (Number(r.or_scrap)||0) + (Number(r.cage_scrap)||0) + (Number(r.ball_scrap)||0) + (Number(r.roller_scrap)||0);
    }, 0);

    const metrics = {
        channel: { in: 0, out: accIn, scrap: 0, visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
        cps: { in: sumSimple(dataCps, 'qty_in', 'qtyIn'), out: sumSimple(dataCps, 'qty_sent', 'qtySent'), scrap: 0, visited: isFlowLoaded ? 'Visited - Channel' : 'Not Visited - Channel' },
        disassembly: { in: sumSimple(dataDismantling, 'qty_in', 'qtyIn'), out: sumSimple(dataDismantling, 'qty_sent', 'qtySent'), scrap: dismScrap, visited: isFlowLoaded ? 'Visited - Channel' : 'Not Visited - Channel' },
        rework: { in: sumSimple(dataRework, 'qty_in', 'qtyIn'), out: sumSimple(dataRework, 'qty_sent', 'qtySent'), scrap: 0, visited: isFlowLoaded ? 'Visited - Channel' : 'Not Visited - Channel' },
        accurate: { in: accIn, out: accOut, scrap: 0, visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
        autoPacking: { in: sumSimple(dataAutopackaging, 'qty_in', 'qtyIn'), out: sumSimple(dataAutopackaging, 'qty_sent', 'qtySent'), scrap: 0, visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
        fps: { in: sumSimple(dataFps, 'qty_in', 'qtyIn'), out: sumSimple(dataFps, 'qty_sent', 'qtySent'), scrap: 0, visited: isFlowLoaded ? 'Finished' : 'Not Visited' },
        commonScrap: { scrap: dismScrap }
    };

    const NodeCard = ({ title, subtitle, icon, type, mIn, mOut, mScrap, visited, borderCls }) => (
        <div className={`pvsm-card ${borderCls}`}>
            <div className="pvsm-card-header">
                <span className="pvsm-card-icon">{icon}</span>
                <div className="pvsm-card-title-area">
                    <h4>{title}</h4>
                    <span>{subtitle}</span>
                </div>
            </div>
            <div className="pvsm-card-metrics">
                {mIn !== undefined && (
                    <div className="pvsm-metric">
                        <span className="pvsm-metric-icon green">↓</span>
                        <label>Incoming</label>
                        <strong className="green">{mIn}</strong>
                        <sub>PCS</sub>
                    </div>
                )}
                {mOut !== undefined && (
                    <div className="pvsm-metric">
                        <span className="pvsm-metric-icon blue">↑</span>
                        <label>Outgoing</label>
                        <strong className="blue">{mOut}</strong>
                        <sub>PCS</sub>
                    </div>
                )}
                {mScrap !== undefined && (
                    <div className="pvsm-metric">
                        <span className="pvsm-metric-icon red">🗑</span>
                        <label>Scrap</label>
                        <strong className="red">{mScrap}</strong>
                        <sub>PCS</sub>
                    </div>
                )}
            </div>
            {visited && (
                <div className="pvsm-card-footer">
                    <span className={`pvsm-badge ${visited.includes('Visited') ? (borderCls==='border-green'?'green':'blue') : ''}`}>{visited}</span>
                </div>
            )}
        </div>
    );

    return (
        <div className="pvsm-wrapper">
            <div className="pvsm-header">
                <div className="pvsm-title">
                    <h2>P-VSM</h2>
                    <span>Process Value Stream Mapping</span>
                </div>
                <div className="pvsm-controls">
                    <div className="pvsm-control-group">
                        <label>Select MO</label>
                        <select className="pvsm-select" value={pvsmMo} onChange={e=>setPvsmMo(e.target.value)}>
                            <option>Select MO</option>
                            {[...new Set(allUniqueMos)].map(m => <option key={m}>{m}</option>)}
                        </select>
                    </div>
                    <div className="pvsm-control-group">
                        <label>Select Type</label>
                        <select className="pvsm-select" value={pvsmType} onChange={e=>setPvsmType(e.target.value)}>
                            <option>Select Type</option>
                            {[...new Set(allUniqueVariants)].map(v => <option key={v}>{v}</option>)}
                        </select>
                    </div>
                    <button className="pvsm-btn-load" onClick={() => setIsFlowLoaded(true)}>
                        ▶ Load Flow
                    </button>
                </div>
            </div>

            <div className="pvsm-canvas">
                <div className="pvsm-grid">
                    
                    {/* ROW 1 */}
                    <div className="node-pos-dmstore">
                        <NodeCard title="DM Store" subtitle="Material Storage" icon="🏛" mIn={0} mOut={0} visited="Not Visited" borderCls="" />
                    </div>
                    <div className="node-pos-sho">
                        <NodeCard title="SHO" subtitle="Shared Handling" icon="📈" mIn={0} mOut={0} mScrap={0} visited="Not Visited" borderCls="" />
                    </div>
                    <div className="node-pos-transit">
                        <NodeCard title="Transit Buffer" subtitle="Buffer" icon="🚚" mIn={0} mOut={0} visited="Not Visited" borderCls="" />
                    </div>
                    <div className="node-pos-channel">
                        <NodeCard title="Channel" subtitle="Production" icon="🖧" mIn={metrics.channel.in} mOut={metrics.channel.out} mScrap={metrics.channel.scrap} visited={metrics.channel.visited} borderCls="" />
                    </div>
                    <div className="node-pos-bearingstore">
                        <NodeCard title="Bearing Storage" subtitle="Storage" icon="📦" mIn={0} mOut={0} visited="Not Visited" borderCls="" />
                    </div>

                    {/* ROW 2 */}
                    <div className="node-pos-cps">
                        <NodeCard title="CPS" subtitle="Storage" icon="🏢" mIn={metrics.cps.in} mOut={metrics.cps.out} visited={metrics.cps.visited} borderCls="border-dashed" />
                    </div>
                    <div className="node-pos-disassembly">
                        <NodeCard title="Disassembly Area" subtitle="Rework" icon="🔧" mIn={metrics.disassembly.in} mOut={metrics.disassembly.out} mScrap={metrics.disassembly.scrap} visited={metrics.disassembly.visited} borderCls="border-dashed" />
                    </div>
                    <div className="node-pos-rework">
                        <NodeCard title="Rework Area" subtitle="Repair" icon="🔄" mIn={metrics.rework.in} mOut={metrics.rework.out} mScrap={metrics.rework.scrap} visited={metrics.rework.visited} borderCls="border-dashed" />
                    </div>
                    <div className="node-pos-accurate">
                        <NodeCard title="Accurate" subtitle="Inspection" icon="🎯" mIn={metrics.accurate.in} mOut={metrics.accurate.out} visited={metrics.accurate.visited} borderCls="border-green" />
                    </div>
                    <div className="node-pos-autopacking">
                        <NodeCard title="Auto Packing" subtitle="Packing" icon="🏭" mIn={metrics.autoPacking.in} mOut={metrics.autoPacking.out} visited={metrics.autoPacking.visited} borderCls="border-green" />
                    </div>

                    {/* ROW 3 */}
                    <div className="node-pos-legend">
                        <div className="pvsm-legend">
                            <h4>Flow Legend</h4>
                            <div className="pvsm-legend-item"><div className="pvsm-legend-line line-green"></div> Material Flow</div>
                            <div className="pvsm-legend-item"><div className="pvsm-legend-line line-red"></div> Return Flow</div>
                            <div className="pvsm-legend-item"><div className="pvsm-legend-line line-orange-dash"></div> Scrap Flow</div>
                        </div>
                    </div>
                    <div className="node-pos-commonscrap">
                        <NodeCard title="Common Scrap" subtitle="Scrap" icon="🗑" mScrap={metrics.commonScrap.scrap} visited="Not Visited" borderCls="border-red" />
                    </div>
                    <div className="node-pos-fps">
                        <NodeCard title="FPS" subtitle="Finished Product" icon="🛡" mIn={metrics.fps.in} mOut={metrics.fps.out} visited={metrics.fps.visited} borderCls="border-green" />
                    </div>

                </div>
            </div>
        </div>
    );
  };
 
  return (
    <div className="afterchannel-container">
      <datalist id="depts-list"><option value="Channel" /><option value="Accurate" /><option value="CPS" /><option value="Rework" /><option value="Dismantling" /><option value="Autopackaging" /><option value="FPS" /><option value="Scrap" /></datalist>
      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'].map(ch => <option key={ch} value={ch} />)}
      </datalist>
      <datalist id="mo-list">
        {dynamicMosList.map(mo => <option key={mo} value={mo} />)}
      </datalist>
      <datalist id="variants-list">
        {dynamicVariantsList.map(v => <option key={v} value={v} />)}
      </datalist>
      
      <div className="ac-header">
        <h1 className="ac-title">Afterchannel Processing</h1>
        <div className="tab-buttons">
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button
              key={tab}
              className={`tab-pill tab-pill-${tab} ${activeTab === tab ? 'tab-pill-active' : ''}`}
              onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily(''); resetComponentScrapStates();}}
            >
              {tab.toUpperCase()}
            </button>
          ))}
          <button
            className={`tab-pill tab-pill-summary ${activeTab === 'summary' ? 'tab-pill-active' : ''}`}
            onClick={() => setActiveTab('summary')}
          >
            📊 SUMMARY
          </button>
          <button
            className={`tab-pill ${activeTab === 'visualFlow' ? 'tab-pill-active' : ''}`}
            onClick={() => setActiveTab('visualFlow')}
          >
            📈 VISUAL FLOW
          </button>
        </div>
      </div>
 
      {activeTab !== 'summary' && activeTab !== 'visualFlow' && (
        <div className="filter-card">
          <div className="filter-row">
            <div className="field-group">
              <label className="field-label">Variant</label>
              <input list="variants-list" value={selectedVariant} onChange={handleVariantChange} placeholder="Select or Type Variant..." className="field-input" required />
            </div>
            <div className="field-group">
              <label className="field-label">MO Number</label>
              <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." className="field-input" required />
            </div>
            <div className="field-group">
              <label className="field-label">Target Production Qty</label>
              <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly className="field-input field-input-readout" />
            </div>
          </div>
          <div className="mode-toggle-row">
            <button type="button" onClick={() => setEntryMode('IN')} className={`mode-btn mode-btn-in ${entryMode === 'IN' ? 'mode-btn-active' : ''}`}>📥 LOG IN (Receiving)</button>
            <button type="button" onClick={() => setEntryMode('OUT')} className={`mode-btn mode-btn-out ${entryMode === 'OUT' ? 'mode-btn-active' : ''}`}>📤 LOG OUT (Dispatch)</button>
            {editingRecord && <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); setBearingFamily(''); resetComponentScrapStates(); }} className="cancel-edit-btn">Cancel Edit</button>}
          </div>
        </div>
      )}
 
      <div className="ac-content">
        {['accurate', 'cps', 'rework', 'autopackaging', 'fps'].includes(activeTab) && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, activeTab)}>
              <fieldset className={`form-fieldset ${entryMode === 'OUT' ? 'form-fieldset-out' : ''}`}>
              <div className="form-card-title">
  {activeTab.toUpperCase()} - {entryMode === "IN"
      ? "Receiving Log"
      : "Dispatch Log"}
</div>

<div className="form-card-body">

  <div className="form-grid-3">
                    {entryMode === 'IN' ? (
                      <>
                        {activeTab === 'cps' && <div className="field-group"><label className="field-label">Item</label><select name="item" defaultValue={editingRecord?.item_type || ''} className="field-input"><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>}
                        <div className="field-group"><label className="field-label">In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                        <div className="field-group"><label className="field-label">Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} className="field-input"><option></option><option>1</option><option>2</option><option>3</option></select></div>
                        {activeTab === 'cps' && <div className="field-group"><label className="field-label">RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} className="field-input"/></div>}
                        {activeTab === 'accurate' && <div className="field-group"><label className="field-label">PC No</label><input type="text" name="pc" defaultValue={editingRecord?.pc_no || ''} className="field-input"/></div>}
                        <div className="field-group"><label className="field-label">Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} className="field-input"/></div>
                        {activeTab === 'cps' && <div className="field-group"><label className="field-label">Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} className="field-input"/></div>}
                        <div className="field-group"><label className="field-label">Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} className="field-input" required/></div>
                      </>
                    ) : (
                      <>
                        {activeTab === 'fps' ? (
                          <div className="field-group"><label className="field-label">Customer Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} className="field-input" required/></div>
                        ) : (
                          <div className="field-group"><label className="field-label">Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} className="field-input"/></div>
                        )}
                        <div className="field-group"><label className="field-label">Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} className="field-input" required/></div>
                        <div className="field-group"><label className="field-label">Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                        <div className="field-group"><label className="field-label">Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} className="field-input"><option></option><option>1</option><option>2</option><option>3</option></select></div>
                      </>
                    )}
                </div>
                </div>
              </fieldset>
              <button type="submit" className={`submit-btn ${entryMode === 'IN' ? 'submit-btn-in' : 'submit-btn-out'}`}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger(activeTab, activeTab.toUpperCase())}
          </div>
        )}
 
        {activeTab === 'dismantling' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              <div className="family-select-bar">
                <label>Bearing Family:</label>
                <select name="bearingFamily" value={bearingFamily} onChange={(e) => setBearingFamily(e.target.value)} required><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select>
              </div>
 
              {entryMode === 'IN' ? (

<fieldset className="form-fieldset">

    <div className="form-card-title">
        ACCURATE - RECEIVING LOG
    </div>

    <div className="form-card-body">

       <div className="form-grid-3">

    <div className="field-group">
        <label className="field-label">In Date</label>
        <input
            type="date"
            name="inDate"
            defaultValue={editingRecord?.in_date || ""}
            className="field-input"
            required
        />
    </div>

    <div className="field-group">
        <label className="field-label">Shift In</label>
        <select
            name="shiftIn"
            defaultValue={editingRecord?.shift_in || ""}
            className="field-input"
        >
            <option></option>
            <option>1</option>
            <option>2</option>
            <option>3</option>
        </select>
    </div>

    <div className="field-group">
        <label className="field-label">PC No</label>
        <input
            type="text"
            name="pc"
            defaultValue={editingRecord?.pc_no || ""}
            className="field-input"
        />
    </div>

    <div className="field-group">
        <label className="field-label">Material In From</label>
        <input
            list="depts-list"
            name="materialInFrom"
            defaultValue={editingRecord?.material_in_from || ""}
            className="field-input"
        />
    </div>

    <div className="field-group">
        <label className="field-label">Qty In</label>
        <input
            type="number"
            name="qtyIn"
            defaultValue={editingRecord?.qty_in || ""}
            className="field-input"
            required
        />
    </div>

</div>

    </div>

</fieldset>
              ) : (
                <fieldset className="form-fieldset form-fieldset-out">
                  <legend>Dismantling - Dispatch Log</legend>
                  
                  <div className="component-outbound-card">
                    <h4>Specific Component Outbound Destinations</h4>
                    
                    <div className="component-row">
                      <div><label>IR Sent Qty</label><input type="number" name="irSent" value={irSentVal} onChange={e=>setIrSentVal(e.target.value)} className="field-input" /></div>
                      <div><label>IR Next Station</label><input list="depts-list" name="irStation" value={irStationVal} onChange={e=>setIrStationVal(e.target.value)} className="field-input" /></div>
                    </div>
                    <div className="component-row">
                      <div><label>OR Sent Qty</label><input type="number" name="orSent" value={orSentVal} onChange={e=>setOrSentVal(e.target.value)} className="field-input" /></div>
                      <div><label>OR Next Station</label><input list="depts-list" name="orStation" value={orStationVal} onChange={e=>setOrStationVal(e.target.value)} className="field-input" /></div>
                    </div>
                    <div className="component-row">
                      <div><label>Cage Sent Qty</label><input type="number" name="cageSent" value={cageSentVal} onChange={e=>setCageSentVal(e.target.value)} className="field-input" /></div>
                      <div><label>Cage Next Station</label><input list="depts-list" name="cageStation" value={cageStationVal} onChange={e=>setCageStationVal(e.target.value)} className="field-input" /></div>
                    </div>
                    <div className="component-row">
                      <div><label>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Sent Qty</label><input type="number" name="rollerSent" value={rollerSentVal} onChange={e=>setRollerSentVal(e.target.value)} className="field-input" /></div>
                      <div><label>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Next Station</label><input list="depts-list" name="rollerStation" value={rollerStationVal} onChange={e=>setRollerStationVal(e.target.value)} className="field-input" /></div>
                    </div>
                  </div>
 
                  <div className="scrap-entry-card">
                    <h4>Component Scrap Entry</h4>
                    <div className="scrap-grid-4">
                      <div><label>IR Scrap</label><input type="number" name="irScrap" value={irScrapVal} onChange={e=>setIrScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>OR Scrap</label><input type="number" name="orScrap" value={orScrapVal} onChange={e=>setOrScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>Cage Scrap</label><input type="number" name="cageScrap" value={cageScrapVal} onChange={e=>setCageScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>Ball/Roll Scrap</label><input type="number" name="ballScrap" value={ballScrapVal} onChange={e=>setBallScrapVal(e.target.value)} className="field-input" /></div>
                    </div>
                  </div>
 
                  <div className="form-grid-3">
                    <div className="field-group"><label className="field-label">Overall Qty Sent (Optional)</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent||''} className="field-input"/></div>
                    <div className="field-group"><label className="field-label">Next Station (Overall)</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station||''} className="field-input"/></div>
                    <div className="field-group"><label className="field-label">Remarks</label><input type="text" name="remark" value={remarkVal} onChange={e=>setRemarkVal(e.target.value)} className="field-input" placeholder="General remarks..."/></div>
                    <div className="field-group"><label className="field-label">Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date||''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                    <div className="field-group"><label className="field-label">Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out||''} className="field-input"><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" className={`submit-btn ${entryMode === 'IN' ? 'submit-btn-in' : 'submit-btn-out'}`}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Dismantling Processing')}
          </div>
        )}
 
        {activeTab === 'summary' && (
          <div className="summary-view">
            <div className="summary-view-header">
              <h2 className="summary-view-title">MO Variant Flow Hierarchy</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="summary-search-input" />
            </div>
 
            <div className="table-scroll">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th className="col-mo">Master Order / Variant</th>
                    <th>Rw IN</th><th>Rw OUT</th>
                    <th>Dism IN</th><th>Dism OUT</th>
                    <th>CPS IN</th><th>CPS OUT</th>
                    <th>Acc IN</th><th>Acc OUT</th>
                    <th>Pkg IN</th><th>Pkg OUT</th>
                    <th>FPS IN</th>
                    <th className="col-scrap">IR Scrp</th>
                    <th className="col-scrap">OR Scrp</th>
                    <th className="col-scrap">Cg Scrp</th>
                    <th className="col-scrap">Rl Scrp</th>
                    <th className="col-scrap">Tot Scrp</th>
                  </tr>
                </thead>
                <tbody>
                  {generateSummaryData().map(moData => (
                    <React.Fragment key={moData.mo}>
                      {/* LEVEL 0: MO ROW */}
                      <tr onClick={() => setExpandedMOs(p => ({...p, [moData.mo]: !p[moData.mo]}))} className={`row-mo ${expandedMOs[moData.mo] ? 'row-mo-expanded' : ''}`}>
                        <td className="mo-toggle-cell">{expandedMOs[moData.mo] ? '▼' : '▶'} {moData.mo}</td>
                        <td>{moData.totals.rwIn || '-'}</td><td>{moData.totals.rwOut || '-'}</td>
                        <td>{moData.totals.disIn || '-'}</td><td className="cell-dis-out">{moData.totals.disOut || '-'}</td>
                        <td>{moData.totals.cpsIn || '-'}</td><td>{moData.totals.cpsOut || '-'}</td>
                        <td>{moData.totals.accIn || '-'}</td><td>{moData.totals.accOut || '-'}</td>
                        <td>{moData.totals.apIn || '-'}</td><td>{moData.totals.apOut || '-'}</td>
                        <td>{moData.totals.fpsIn || '-'}</td>
                        <td className="cell-scrap-sub">{moData.totals.irScrap || '-'}</td>
                        <td className="cell-scrap-sub">{moData.totals.orScrap || '-'}</td>
                        <td className="cell-scrap-sub">{moData.totals.cageScrap || '-'}</td>
                        <td className="cell-scrap-sub">{moData.totals.ballScrap || '-'}</td>
                        <td className="cell-scrap-total">{moData.totals.totalScrap || '-'}</td>
                      </tr>
 
                      {expandedMOs[moData.mo] && Object.entries(moData.variants).map(([variant, vData]) => {
                        const vKey = `${moData.mo}-${variant}`;
                        return (
                          <React.Fragment key={variant}>
                            {/* LEVEL 1: VARIANT ROW */}
                            <tr onClick={() => setExpandedVariants(p => ({...p, [vKey]: !p[vKey]}))} className="row-variant">
                              <td className="variant-toggle-cell">{expandedVariants[vKey] ? '▼' : '▶'} {variant}</td>
                              <td>{vData.rwIn || '-'}</td><td>{vData.rwOut || '-'}</td>
                              <td>{vData.disIn || '-'}</td><td className="cell-dis-out">{vData.disOut || '-'}</td>
                              <td>{vData.cpsIn || '-'}</td><td>{vData.cpsOut || '-'}</td>
                              <td>{vData.accIn || '-'}</td><td>{vData.accOut || '-'}</td>
                              <td>{vData.apIn || '-'}</td><td>{vData.apOut || '-'}</td>
                              <td>{vData.fpsIn || '-'}</td>
                              <td className="cell-scrap-sub">{vData.irScrap || '-'}</td>
                              <td className="cell-scrap-sub">{vData.orScrap || '-'}</td>
                              <td className="cell-scrap-sub">{vData.cageScrap || '-'}</td>
                              <td className="cell-scrap-sub">{vData.ballScrap || '-'}</td>
                              <td className="cell-scrap-total">{vData.totalScrap || '-'}</td>
                            </tr>
                                                        
                             {/* LEVEL 2: COMPONENT DISPATCH DETAILS */}
                            {expandedVariants[vKey] && (
                              <tr><td colSpan="17" style={{padding: 0}}>{renderMoDispatchDetails(vData.records)}</td></tr>
                            )}
                          </React.Fragment>
                        );
                      })}
 
                      {/* MO BOTTOM TOTAL ROW */}
                      {expandedMOs[moData.mo] && (
                        <tr className="row-total">
                          <td className="label-cell">TOTAL FOR {moData.mo}:</td>
                          <td>{moData.totals.rwIn || '-'}</td><td>{moData.totals.rwOut || '-'}</td>
                          <td>{moData.totals.disIn || '-'}</td><td className="cell-dis-out">{moData.totals.disOut || '-'}</td>
                          <td>{moData.totals.cpsIn || '-'}</td><td>{moData.totals.cpsOut || '-'}</td>
                          <td>{moData.totals.accIn || '-'}</td><td>{moData.totals.accOut || '-'}</td>
                          <td>{moData.totals.apIn || '-'}</td><td>{moData.totals.apOut || '-'}</td>
                          <td>{moData.totals.fpsIn || '-'}</td>
                          <td colSpan="5" className="scrap-grand-total-cell">Grand Total Scrap: {moData.totals.totalScrap}</td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ================= NEW VISUAL FLOW VIEW (P-VSM UI) ================= */}
        {activeTab === 'visualFlow' && renderPVSMFlow()}
      </div>
    </div>
  );
};
 
export default Afterchannel;
