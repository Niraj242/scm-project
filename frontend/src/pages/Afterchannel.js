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
 
  // Disassembly Scrap/Dispatch states
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
 
  // P-VSM Visual Flow Filters
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
          dismantling: json.data?.vibration || [],
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
 
  const allUniqueVariants = [...new Set(Object.values(moCache).flatMap(rows => rows.map(r => getTypeFromRow(r))))].filter(Boolean).sort();
  const allUniqueMos = Object.keys(moCache).sort();
 
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
      type: selectedVariant.toUpperCase(),
      bearingFamily: bearingFamily || null
    };
 
    const numFields = [
      'qtyIn', 'qtySent', 'ballScrap', 'rollerScrap', 'cageScrap', 'irScrap', 'orScrap',
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
    }
 
    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}`, {
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
    setSelectedVariant(record.bearing_type || record.type || '');
    setBearingFamily(record.bearing_family || record.bearingFamily || '');
    setEntryMode((record.qty_sent || record.qtySent) ? 'OUT' : 'IN');
    
    setIrScrapVal(record.ir_scrap ?? ''); setOrScrapVal(record.or_scrap ?? '');
    setCageScrapVal(record.cage_scrap ?? ''); setBallScrapVal(record.ball_scrap ?? '');
    setRollerScrapVal(record.roller_scrap ?? ''); setRemarkVal(record.remark || '');
    
    setIrSentVal(record.ir_sent ?? ''); setIrStationVal(record.ir_station || '');
    setOrSentVal(record.or_sent ?? ''); setOrStationVal(record.or_station || '');
    setCageSentVal(record.cage_sent ?? ''); setCageStationVal(record.cage_station || '');
    setRollerSentVal(record.roller_sent ?? ''); setRollerStationVal(record.roller_station || '');
 
    setEditingRecord(record);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
 
  const handleDelete = async (id, tab) => {
    if(!window.confirm("Are you sure you want to delete this entry permanently?")) return;
    try {
      const response = await fetch(`${API}/api/afterchannel/${tab}/${id}`, { method: 'DELETE' });
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
    const safeLedgers = { accurate: ledgers.accurate||[], cps: ledgers.cps||[], rework: ledgers.rework||[], dismantling: ledgers.dismantling||[], autopackaging: ledgers.autopackaging||[], fps: ledgers.fps||[] };
    const allLists = [
      ...safeLedgers.accurate.map(r=>({...r, _dept:'accurate'})), ...safeLedgers.cps.map(r=>({...r, _dept:'cps'})), 
      ...safeLedgers.rework.map(r=>({...r, _dept:'rework'})), ...safeLedgers.dismantling.map(r=>({...r, _dept:'dismantling'})), 
      ...safeLedgers.autopackaging.map(r=>({...r, _dept:'autopackaging'})), ...safeLedgers.fps.map(r=>({...r, _dept:'fps'}))
    ];
    
    const summaryMap = {};
    allLists.forEach(item => {
      if (!item.mo) return;
      const mo = item.mo.toUpperCase();
      let variant = (item.bearing_type || item.type || '').toUpperCase();
      if (!variant) variant = 'OVERALL';
 
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
    const outRecs = records.filter(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0);
    if (outRecs.length === 0) return <div className="dispatch-empty-note">No dispatch/scrap events recorded.</div>;
    const grouped = outRecs.reduce((acc, curr) => { if(!acc[curr._dept]) acc[curr._dept] = []; acc[curr._dept].push(curr); return acc; }, {});
 
    return (
      <div className="dispatch-detail-panel">
        {Object.keys(grouped).map(dept => (
          <div key={dept} className="dispatch-dept-card">
            <h4>{dept.toUpperCase()} Activity</h4>
            <div className="dispatch-events">
              {grouped[dept].map((r, i) => (
                <div key={i} className="dispatch-event">
                  {r.qty_sent > 0 && <div><strong className="qty-highlight">{r.qty_sent}</strong> sent to <strong>{r.next_station || 'N/A'}</strong></div>}
                  {r.ir_sent > 0 && <div><strong className="qty-highlight">{r.ir_sent} IR</strong> sent to <strong>{r.ir_station || 'N/A'}</strong></div>}
                  {r.or_sent > 0 && <div><strong className="qty-highlight">{r.or_sent} OR</strong> sent to <strong>{r.or_station || 'N/A'}</strong></div>}
                  {r.cage_sent > 0 && <div><strong className="qty-highlight">{r.cage_sent} Cage</strong> sent to <strong>{r.cage_station || 'N/A'}</strong></div>}
                  {r.roller_sent > 0 && <div><strong className="qty-highlight">{r.roller_sent} Component</strong> sent to <strong>{r.roller_station || 'N/A'}</strong></div>}
                  {(r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0) && (
                      <div className="scrap-line">
                          Scrap: {[r.ir_scrap && `${r.ir_scrap} IR`, r.or_scrap && `${r.or_scrap} OR`, r.cage_scrap && `${r.cage_scrap} Cage`, (r.ball_scrap||r.roller_scrap) && `${r.ball_scrap||r.roller_scrap} Core`].filter(Boolean).join(', ')}
                      </div>
                  )}
                  <span className="meta-line">Date: {r.out_date || r.outDate} | Shift: {r.shift_out || '-'}</span>
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
    const deptData = ledgers[deptKey] || [];
    const records = deptData.filter(l => {
      const search = ledgerSearchQuery.toUpperCase();
      return (l.mo || '').toUpperCase().includes(search) || (l.bearing_type || l.type || '').toUpperCase().includes(search);
    });
 
    if (records.length === 0) return (
      <div className="ledger-empty-card">
        <div className="ledger-empty-header">
          <span className="ledger-empty-title">{deptName} Log</span>
          <input type="text" placeholder="Search..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="field-input" style={{width: '250px'}} />
        </div>
        No items recorded.
      </div>
    );
 
    return (
      <div className="ledger-card">
        <div className="ledger-card-header">
          <span>{deptName} Ledger Logs</span>
          <input type="text" placeholder="Search logs..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="ledger-search-input" />
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>MO</th><th>Variant</th><th>Date IN</th><th>Source</th><th className="col-qty-in">Qty IN</th><th>Date OUT</th><th>Next Location</th><th className="col-qty-out">Qty OUT</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i}>
                  <td className="cell-strong">{r.mo || '-'}</td>
                  <td className="cell-strong">{r.bearing_type || r.type || '-'}</td>
                  <td>{r.in_date || r.inDate || '-'}</td>
                  <td>{r.material_in_from || r.materialInFrom || '-'}</td>
                  <td className="cell-qty-in">{r.qty_in || r.qtyIn || '-'}</td>
                  <td>{r.out_date || r.outDate || '-'}</td>
                  <td className={isScrapStation(r.next_station || r.nextStation) ? 'cell-scrap-flag' : ''}>
                    {r.next_station || r.nextStation || '-'}
                  </td>
                  <td className="cell-qty-out">{r.qty_sent || r.qtySent || '-'}</td>
                  <td>
                    <button type="button" onClick={() => handleEdit(r)} className="row-action-btn edit-tint">✏️</button>
                    <button type="button" onClick={() => handleDelete(r.id, deptKey)} className="row-action-btn delete-tint">🗑️</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderPVSMFlow = () => {
    const allLedgerMos = Object.values(ledgers).flat().map(r => (r.mo || '').trim().toUpperCase()).filter(Boolean);
    const combinedMosList = [...new Set([...allUniqueMos, ...allLedgerMos])].sort();

    const getFiltered = (deptKey) => {
        let data = ledgers[deptKey] || [];
        if (isFlowLoaded && pvsmMo && pvsmMo !== 'Select MO') data = data.filter(r => (r.mo || '').toUpperCase() === pvsmMo.toUpperCase());
        if (isFlowLoaded && pvsmType && pvsmType !== 'Select Type') data = data.filter(r => (r.bearing_type || r.type || '').toUpperCase() === pvsmType.toUpperCase());
        return isFlowLoaded ? data : [];
    };

    const dAcc = getFiltered('accurate');
    const dCps = getFiltered('cps');
    const dRew = getFiltered('rework');
    const dDis = getFiltered('dismantling');
    const dAp = getFiltered('autopackaging');
    const dFps = getFiltered('fps');

    const accIn = dAcc.reduce((s, r) => !isLoopback('accurate', r.material_in_from) ? s + (Number(r.qty_in) || 0) : s, 0);
    const accOut = dAcc.reduce((s, r) => !isLoopback('accurate', r.next_station) ? s + (Number(r.qty_sent) || 0) : s, 0);
    const cpsIn = dCps.reduce((s, r) => !isLoopback('cps', r.material_in_from) ? s + (Number(r.qty_in) || 0) : s, 0);
    const cpsOut = dCps.reduce((s, r) => !isLoopback('cps', r.next_station) ? s + (Number(r.qty_sent) || 0) : s, 0);
    const apIn = dAp.reduce((s, r) => !isLoopback('autopackaging', r.material_in_from) ? s + (Number(r.qty_in) || 0) : s, 0);
    const apOut = dAp.reduce((s, r) => !isLoopback('autopackaging', r.next_station) ? s + (Number(r.qty_sent) || 0) : s, 0);
    const fpsIn = dFps.reduce((s, r) => s + (Number(r.qty_in) || 0), 0);
    const rwIn = dRew.reduce((s, r) => s + (Number(r.qty_in) || 0), 0);
    const rwOut = dRew.reduce((s, r) => s + (Number(r.qty_sent) || 0), 0);
    
    const disIn = dDis.reduce((s, r) => s + (Number(r.qty_in) || 0), 0);
    const disOutGen = dDis.reduce((s, r) => s + (Number(r.qty_sent) || 0), 0);
    const irScrap = dDis.reduce((s, r) => s + (Number(r.ir_scrap) || 0), 0);
    const orScrap = dDis.reduce((s, r) => s + (Number(r.or_scrap) || 0), 0);
    const cageScrap = dDis.reduce((s, r) => s + (Number(r.cage_scrap) || 0), 0);
    const ballScrap = dDis.reduce((s, r) => s + (Number(r.ball_scrap || r.roller_scrap) || 0), 0);
    const irSent = dDis.reduce((s, r) => s + (Number(r.ir_sent) || 0), 0);
    const orSent = dDis.reduce((s, r) => s + (Number(r.or_sent) || 0), 0);

    const netDisassemblyOut = disOutGen + Math.min(irSent + irScrap, orSent + orScrap);
    const totalScrap = irScrap + orScrap + cageScrap + ballScrap;

    const NodeCard = ({ title, input, output, colorClass }) => (
      <div className={`pvsm-node-card ${colorClass}`}>
        <div className="pvsm-card-header">{title}</div>
        <div className="pvsm-card-metrics">
          <div className="pvsm-metric"><label>TOTAL IN</label><strong className="green">{input || '-'}</strong></div>
          <div className="pvsm-metric"><label>TOTAL OUT</label><strong className="blue">{output || '-'}</strong></div>
        </div>
      </div>
    );

    return (
      <div className="summary-view animate-fade-in">
        <div className="pvsm-control-bar">
          <select value={pvsmMo} onChange={e => {setPvsmMo(e.target.value); setIsFlowLoaded(false);}} className="field-input">
            <option>Select MO</option>
            {combinedMosList.map(mo => <option key={mo} value={mo}>{mo}</option>)}
          </select>
          <button type="button" onClick={() => setIsFlowLoaded(true)} className="submit-btn submit-btn-in" style={{marginTop:0}}>GENERATE VALUE FLOW</button>
        </div>

        {isFlowLoaded && (
          <div className="pvsm-canvas-container">
            <svg className="pvsm-svg-overlay">
              <defs><marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#94a3b8"/></marker></defs>
              <path d="M 180 90 L 335 90" markerEnd="url(#arrow)" />
              <path d="M 500 90 L 535 90" markerEnd="url(#arrow)" />
              <path d="M 620 130 Q 620 180 980 180 L 980 155" markerEnd="url(#arrow)" />
              <path d="M 700 225 L 713 225" markerEnd="url(#arrow)" className="dashed-arrow" />
              <path d="M 880 225 L 893 225" markerEnd="url(#arrow)" />
              <path d="M 1060 225 L 1073 225" markerEnd="url(#arrow)" />
              <path d="M 1160 290 Q 1160 330 980 330 L 980 315" markerEnd="url(#arrow)" />
              <path d="M 620 290 L 620 312" markerEnd="url(#arrow)" className="dashed-arrow" />
            </svg>
            <div className="pvsm-grid">
              <div className="node-pos-dmstore"><NodeCard title="1. MATERIAL STORAGE" input="-" output="-" colorClass="blue-border" /></div>
              <div className="node-pos-disassembly"><NodeCard title="4. DISASSEMBLY LINE" input={disIn} output={netDisassemblyOut} colorClass="red-border" /></div>
              <div className="node-pos-rework"><NodeCard title="5. REWORK CELL" input={rwIn} output={rwOut} colorClass="orange-border" /></div>
              <div className="node-pos-accurate"><NodeCard title="2. ACCURATE ASSEMBLY" input={accIn} output={accOut} colorClass="navy-border" /></div>
              <div className="node-pos-autopacking"><NodeCard title="3. AUTOPACKAGING" input={apIn} output={apOut} colorClass="teal-border" /></div>
              <div className="node-pos-cps"><NodeCard title="6. CPS VALUE STREAM" input={cpsIn} output={cpsOut} colorClass="purple-border" /></div>
              <div className="node-pos-fps"><NodeCard title="7. FPS STORAGE" input={fpsIn} output="-" colorClass="green-border" /></div>
              <div className="node-pos-scrap">
                <div className="pvsm-node-card red-border text-center">
                  <div className="pvsm-card-header background-red">SCRAP DISPOSAL CONTAINER</div>
                  <div className="pvsm-card-metrics grid-4">
                    <div className="pvsm-metric"><label>IR</label><strong>{irScrap || '-'}</strong></div>
                    <div className="pvsm-metric"><label>OR</label><strong>{orScrap || '-'}</strong></div>
                    <div className="pvsm-metric"><label>CAGE</label><strong>{cageScrap || '-'}</strong></div>
                    <div className="pvsm-metric"><label>BALL/ROLLER</label><strong>{ballScrap || '-'}</strong></div>
                  </div>
                  <div className="pvsm-card-footer"><span className="pvsm-badge red">Grand Total Scrap: {totalScrap}</span></div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const summaryData = generateSummaryData();

  return (
    <div className="afterchannel-container">
      <datalist id="depts-list">
        <option value="Accurate Assembly"/><option value="CPS Line"/><option value="Rework Room"/><option value="Disassembly Line"/><option value="Autopackaging"/><option value="FPS Yield Store"/><option value="Scrap Container"/>
      </datalist>
      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06'].map(ch => <option key={ch} value={ch} />)}
      </datalist>
      <datalist id="mo-list">{dynamicMosList.map(mo => <option key={mo} value={mo} />)}</datalist>
      <datalist id="variants-list">{dynamicVariantsList.map(v => <option key={v} value={v} />)}</datalist>
 
      <div className="ac-header">
        <h1 className="ac-title">Afterchannel Processing Operations</h1>
        <div className="tab-buttons">
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={`tab-pill tab-pill-${tab} ${activeTab === tab ? 'tab-pill-active' : ''}`} onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily(''); resetComponentScrapStates();}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={`tab-pill tab-pill-summary ${activeTab === 'summary' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('summary')}>📊 SUMMARY</button>
          <button className={`tab-pill ${activeTab === 'visualFlow' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('visualFlow')}>📈 FACTORY FLOW</button>
        </div>
      </div>
 
      <div className="tab-content">
        {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].includes(activeTab) && (
          <div>
            <div className="filter-card">
              <div className="filter-row">
                <div className="field-group">
                  <label className="field-label">Master Order No (MO)</label>
                  <input list="mo-list" value={moNumber} onChange={(e)=>setMoNumber(e.target.value.toUpperCase())} onBlur={handleMoBlur} placeholder="Type MO..." className="field-input" required/>
                </div>
                <div className="field-group">
                  <label className="field-label">Component Design / Variant</label>
                  <input list="variants-list" value={selectedVariant} onChange={handleVariantChange} placeholder="Select Variant..." className="field-input" required/>
                </div>
                <div className="field-group">
                  <label className="field-label">Scheduled Order Size</label>
                  <input type="text" value={actualProductionQty || '-'} className="field-input field-input-readout" readOnly/>
                </div>
              </div>
              
              <div className="mode-toggle-row">
                <button type="button" className={`mode-btn mode-btn-in ${entryMode === 'IN' ? 'mode-btn-active' : ''}`} onClick={() => setEntryMode('IN')}>📥 LINE REGISTRATION (IN)</button>
                <button type="button" className={`mode-btn mode-btn-out ${entryMode === 'OUT' ? 'mode-btn-active' : ''}`} onClick={() => setEntryMode('OUT')}>📤 OUTBOUND SYSTEM (OUT)</button>
                {editingRecord && <button type="button" onClick={() => {setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); resetComponentScrapStates();}} className="cancel-edit-btn">Cancel Edit</button>}
              </div>
            </div>
 
            <form onSubmit={(e) => handleFormSubmit(e, activeTab)} className={`form-fieldset ${entryMode === 'OUT' ? 'form-fieldset-out' : ''}`}>
              <div className="form-card-title">{activeTab.toUpperCase()} - {entryMode === 'IN' ? 'RECEIVE WORKPIECE' : 'DISPATCH ROUTE'}</div>
              <div className="form-card-body">
                {activeTab === 'dismantling' && entryMode === 'OUT' && (
                  <div className="family-select-bar">
                    <label>Bearing Structure Family:</label>
                    <select name="bearingFamily" value={bearingFamily} onChange={e=>setBearingFamily(e.target.value)} required>
                      <option value=""></option><option value="DGBB">DGBB (Deep Groove Ball Bearing)</option><option value="TRB">TRB (Tapered Roller Bearing)</option>
                    </select>
                  </div>
                )}
 
                {activeTab === 'dismantling' && entryMode === 'OUT' && (
                  <div className="scrap-entry-card">
                    <h4>Component Scrap Collection Containers</h4>
                    <div className="scrap-grid-4">
                      <div><label>Inner Ring (IR) Scrap</label><input type="number" name="irScrap" value={irScrapVal} onChange={e=>setIrScrapVal(e.target.value)} className="field-input"/></div>
                      <div><label>Outer Ring (OR) Scrap</label><input type="number" name="orScrap" value={orScrapVal} onChange={e=>setOrScrapVal(e.target.value)} className="field-input"/></div>
                      <div><label>Retaining Cage Scrap</label><input type="number" name="cageScrap" value={cageScrapVal} onChange={e=>setCageScrapVal(e.target.value)} className="field-input"/></div>
                      <div><label>{bearingFamily === 'TRB' ? 'Tapered Rollers' : 'Steel Balls'} Scrap</label><input type="number" name={bearingFamily === 'TRB' ? 'rollerScrap' : 'ballScrap'} value={bearingFamily === 'TRB' ? rollerScrapVal : ballScrapVal} onChange={e=> bearingFamily === 'TRB' ? setRollerScrapVal(e.target.value) : setBallScrapVal(e.target.value)} className="field-input"/></div>
                    </div>
                  </div>
                )}
 
                {activeTab === 'dismantling' && entryMode === 'OUT' && (
                  <div className="component-outbound-card">
                    <h4>Segregated Component Flow Dispatches</h4>
                    <div className="component-row">
                      <div><label>IR Dispatch Count</label><input type="number" name="irSent" value={irSentVal} onChange={e=>setIrSentVal(e.target.value)} className="field-input"/></div>
                      <div><label>IR Station Destination</label><input list="depts-list" name="irStation" value={irStationVal} onChange={e=>setIrStationVal(e.target.value)} className="field-input"/></div>
                    </div>
                    <div className="component-row">
                      <div><label>OR Dispatch Count</label><input type="number" name="orSent" value={orSentVal} onChange={e=>setOrSentVal(e.target.value)} className="field-input"/></div>
                      <div><label>OR Station Destination</label><input list="depts-list" name="orStation" value={orStationVal} onChange={e=>setOrStationVal(e.target.value)} className="field-input"/></div>
                    </div>
                    <div className="component-row">
                      <div><label>Cage Dispatch Count</label><input type="number" name="cageSent" value={cageSentVal} onChange={e=>setCageSentVal(e.target.value)} className="field-input"/></div>
                      <div><label>Cage Station Destination</label><input list="depts-list" name="cageStation" value={cageStationVal} onChange={e=>setCageStationVal(e.target.value)} className="field-input"/></div>
                    </div>
                    <div className="component-row">
                      <div><label>Rollers/Balls Sent</label><input type="number" name="rollerSent" value={rollerSentVal} onChange={e=>setRollerSentVal(e.target.value)} className="field-input"/></div>
                      <div><label>Rollers/Balls Destination</label><input list="depts-list" name="rollerStation" value={rollerStationVal} onChange={e=>setRollerStationVal(e.target.value)} className="field-input"/></div>
                    </div>
                  </div>
                )}
 
                <div className="form-grid-3">
                  {entryMode === 'IN' ? (
                    <>
                      <div className="field-group"><label className="field-label">Transaction Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} className="field-input" required/></div>
                      <div className="field-group"><label className="field-label">Production Shift</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} className="field-input" required><option></option><option>1</option><option>2</option><option>3</option></select></div>
                      <div className="field-group"><label className="field-label">Material Source</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} className="field-input"/></div>
                      {activeTab === 'accurate' && <div className="field-group"><label className="field-label">PC Node</label><input type="text" name="pc" defaultValue={editingRecord?.pc || ''} className="field-input"/></div>}
                      {activeTab === 'cps' && <div className="field-group"><label className="field-label">Channel Designation</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} className="field-input"/></div>}
                      <div className="field-group"><label className="field-label">Qty Received</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} className="field-input" required/></div>
                    </>
                  ) : (
                    <>
                      {activeTab === 'fps' ? (
                        <div className="field-group"><label className="field-label">Customer Contract Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} className="field-input" required/></div>
                      ) : (
                        <div className="field-group"><label className="field-label">Next Downstream Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} className="field-input"/></div>
                      )}
                      <div className="field-group"><label className="field-label">Qty Sent / Finished</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} className="field-input" required={activeTab !== 'dismantling'}/></div>
                      <div className="field-group"><label className="field-label">Release Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                      <div className="field-group"><label className="field-label">Outbound Shift</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} className="field-input" required><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    </>
                  )}
                </div>
 
                {entryMode === 'OUT' && (
                  <div className="field-group" style={{marginTop: '15px'}}>
                    <label className="field-label">Quality Log Remarks</label>
                    <textarea name="remark" value={remarkVal} onChange={e=>setRemarkVal(e.target.value)} className="field-input" rows="2" style={{resize: 'vertical'}}/>
                  </div>
                )}
              </div>
              <div style={{padding: '0 24px 24px 24px', background: '#fff'}}>
                <button type="submit" className={`submit-btn ${entryMode === 'IN' ? 'submit-btn-in' : 'submit-btn-out'}`}>
                  {editingRecord ? '💾 COMMIT CHANGE' : '⚡ RECORD ENTRY TRANSACTION'}
                </button>
              </div>
            </form>
 
            <div style={{marginTop: '30px'}}>{renderDepartmentLedger(activeTab, activeTab.toUpperCase())}</div>
          </div>
        )}
 
        {activeTab === 'summary' && (
          <div className="summary-view animate-fade-in">
            <div className="summary-view-header">
              <h3>Global Batch Ledger Tracking Matrix</h3>
              <input type="text" placeholder="Filter Master Order..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} className="ledger-search-input" style={{width: '300px'}} />
            </div>
            
            <div className="table-scroll">
              <table className="summary-data-table">
                <thead>
                  <tr className="main-header">
                    <th rowSpan="2">Master Order (MO)</th>
                    <th colSpan="2" className="group-accurate">Accurate</th>
                    <th colSpan="2" className="group-cps">CPS</th>
                    <th colSpan="2" className="group-rework">Rework</th>
                    <th colSpan="2" className="group-dis">Disassembly</th>
                    <th colSpan="2" className="group-ap">AutoPack</th>
                    <th className="group-fps">FPS</th>
                    <th rowSpan="2" style={{background: '#f1f5f9', color: '#334155'}}>Scrap Log</th>
                  </tr>
                  <tr className="sub-header">
                    <th className="group-accurate">IN</th><th className="group-accurate">OUT</th>
                    <th className="group-cps">IN</th><th className="group-cps">OUT</th>
                    <th className="group-rework">IN</th><th className="group-rework">OUT</th>
                    <th className="group-dis">IN</th><th className="group-dis">OUT</th>
                    <th className="group-ap">IN</th><th className="group-ap">OUT</th>
                    <th className="group-fps">YIELD</th>
                  </tr>
                </thead>
                <tbody>
                  {summaryData.map((moData) => (
                    <React.Fragment key={moData.mo}>
                      <tr className="row-mo-header" onClick={() => setExpandedMOs(prev => ({ ...prev, [moData.mo]: !prev[moData.mo] }))}>
                        <td className="cell-mo-expand">
                          <span className="expand-chevron">{expandedMOs[moData.mo] ? '▼' : '▶'}</span>
                          <strong>{moData.mo}</strong>
                        </td>
                        <td>{moData.totals.accIn || '-'}</td><td>{moData.totals.accOut || '-'}</td>
                        <td>{moData.totals.cpsIn || '-'}</td><td>{moData.totals.cpsOut || '-'}</td>
                        <td>{moData.totals.rwIn || '-'}</td><td>{moData.totals.rwOut || '-'}</td>
                        <td>{moData.totals.disIn || '-'}</td><td className="cell-dis-out">{moData.totals.disOut || '-'}</td>
                        <td>{moData.totals.apIn || '-'}</td><td>{moData.totals.apOut || '-'}</td>
                        <td>{moData.totals.fpsIn || '-'}</td>
                        <td className="scrap-total-cell">⚠️ {moData.totals.totalScrap}</td>
                      </tr>
 
                      {expandedMOs[moData.mo] && Object.keys(moData.variants).map(vName => {
                        const vData = moData.variants[vName];
                        const variantKey = `${moData.mo}-${vName}`;
                        return (
                          <React.Fragment key={vName}>
                            <tr className="row-variant" onClick={() => setExpandedVariants(prev => ({ ...prev, [variantKey]: !prev[variantKey] }))}>
                              <td className="cell-variant-indent">
                                <span className="expand-chevron-sub">{expandedVariants[variantKey] ? '▼' : '▶'}</span>
                                {vName}
                              </td>
                              <td>{vData.accIn || '-'}</td><td>{vData.accOut || '-'}</td>
                              <td>{vData.cpsIn || '-'}</td><td>{vData.cpsOut || '-'}</td>
                              <td>{vData.rwIn || '-'}</td><td>{vData.rwOut || '-'}</td>
                              <td>{vData.disIn || '-'}</td><td className="cell-dis-out">{vData.disOut || '-'}</td>
                              <td>{vData.apIn || '-'}</td><td>{vData.apOut || '-'}</td>
                              <td>{vData.fpsIn || '-'}</td>
                              <td className="scrap-sub-cell">({vData.totalScrap})</td>
                            </tr>
                            {expandedVariants[variantKey] && (
                              <tr><td colSpan="13" style={{padding: 0}}>{renderMoDispatchDetails(vData.records)}</td></tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
 
        {activeTab === 'visualFlow' && renderPVSMFlow()}
      </div>
    </div>
  );
};
 
export default Afterchannel;
