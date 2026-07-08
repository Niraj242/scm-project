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
 
  // Top Level Family state for Rework/Dismantling
  const [bearingFamily, setBearingFamily] = useState(''); 
 
  // Component Scraps & Dispatches
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

  // --- NEW VISUAL FLOW STATES ---
  const [selectedFlowNode, setSelectedFlowNode] = useState(null);
  const [flowFilterMo, setFlowFilterMo] = useState('');
 
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
 
  // Two-way cross filter engines
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
 
  // --- CORE SUMMARY HIERARCHY LOGIC WITH DOUBLE-COUNT PREVENTION ---
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
    const outRecs = records.filter(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0);
    if (outRecs.length === 0) return <div className="dispatch-empty-note" style={{padding: '10px'}}>No dispatch/scrap events recorded here yet.</div>;
    
    const grouped = outRecs.reduce((acc, curr) => {
      if(!acc[curr._dept]) acc[curr._dept] = [];
      acc[curr._dept].push(curr);
      return acc;
    }, {});
    
    return (
      <div style={{display: 'flex', gap: '15px', padding: '15px', background: '#f8fafc', flexWrap: 'wrap'}}>
        {Object.entries(grouped).map(([dept, evts]) => (
          <div key={dept} className="dispatch-dept-card" style={{flex: '1 1 200px', minWidth: '250px'}}>
            <h4>{dept} DISPATCHES</h4>
            <div className="dispatch-events">
              {evts.map((e, idx) => (
                <div key={idx} className="dispatch-event">
                  {e.qty_sent > 0 && <span>Sent <strong className="qty-highlight">{e.qty_sent}</strong> to {e.next_station || 'Unknown'}</span>}
                  {(e.ir_sent > 0 || e.or_sent > 0) && (
                    <div style={{marginTop: '5px'}}>
                      {e.ir_sent > 0 && <div>IR Sent: <strong>{e.ir_sent}</strong> ({e.ir_station})</div>}
                      {e.or_sent > 0 && <div>OR Sent: <strong>{e.or_sent}</strong> ({e.or_station})</div>}
                      {e.cage_sent > 0 && <div>Cage Sent: <strong>{e.cage_sent}</strong></div>}
                      {e.roller_sent > 0 && <div>Roller Sent: <strong>{e.roller_sent}</strong></div>}
                    </div>
                  )}
                  {(e.ir_scrap > 0 || e.or_scrap > 0 || e.cage_scrap > 0 || e.ball_scrap > 0) && (
                    <div className="scrap-line">
                      Scrap: {e.ir_scrap > 0 && `IR(${e.ir_scrap}) `} {e.or_scrap > 0 && `OR(${e.or_scrap}) `} 
                      {e.cage_scrap > 0 && `Cage(${e.cage_scrap}) `} {e.ball_scrap > 0 && `Ball/Roll(${e.ball_scrap})`}
                    </div>
                  )}
                  {e.remark && <div className="remark-line">"{e.remark}"</div>}
                  <small className="meta-line">{e.out_date} | {e.shift_out}</small>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // --- NEW VISUAL FLOW RENDER LOGIC ---
  const renderVisualFlow = () => {
    const filterData = (ledgerArray) => {
      if (!ledgerArray) return [];
      return ledgerArray.filter(record => 
        flowFilterMo ? (record.mo || '').toUpperCase() === flowFilterMo.toUpperCase() : true
      );
    };

    const accData = filterData(ledgers.accurate);
    const cpsData = filterData(ledgers.cps);
    const rwData = filterData(ledgers.rework);
    const disData = filterData(ledgers.dismantling);
    const apData = filterData(ledgers.autopackaging);
    const fpsData = filterData(ledgers.fps);

    const accurateIn = accData.filter(r => r.qty_in || r.qtyIn).reduce((sum, r) => sum + Number(r.qty_in || r.qtyIn || 0), 0);
    
    const getDispatchCount = (dataList, destKeyword) => {
        return dataList.filter(r => 
            (r.qty_sent || r.qtySent) && 
            (r.next_station || r.nextStation || '').toLowerCase().includes(destKeyword.toLowerCase())
        ).reduce((sum, r) => sum + Number(r.qty_sent || r.qtySent || 0), 0);
    };

    const accurateToCPS = getDispatchCount(accData, 'cps');
    const accurateToRW = getDispatchCount(accData, 'rework');
    const accurateToDis = getDispatchCount(accData, 'dismantling') + getDispatchCount(accData, 'vibration');
    const accurateToAP = getDispatchCount(accData, 'autopackaging');
    const accurateToFPS = getDispatchCount(accData, 'fps');

    const netAccurateOut = accurateToCPS + accurateToRW + accurateToAP + accurateToFPS + accurateToDis; 
    const getGeneralOut = (dataList) => dataList.filter(r => r.qty_sent || r.qtySent).reduce((sum, r) => sum + Number(r.qty_sent || r.qtySent || 0), 0);

    const nodes = {
      channel: { title: "Channel Out", in: 0, out: accurateIn, color: 'bg-green' },
      accurate: { title: "Accurate", in: accurateIn, out: netAccurateOut, color: 'bg-blue' },
      cps: { title: "CPS", in: accurateToCPS, out: getGeneralOut(cpsData), color: 'bg-amber' },
      rework: { title: "Rework", in: accurateToRW, out: getGeneralOut(rwData), color: 'bg-violet' },
      dismantling: { title: "Dismantling", in: accurateToDis, out: getGeneralOut(disData), color: 'bg-red' },
      autopacking: { title: "Autopackaging", in: accurateToAP, out: getGeneralOut(apData), color: 'bg-green' },
      fps: { title: "FPS", in: accurateToFPS, out: getGeneralOut(fpsData), color: 'bg-blue' }
    };

    const allMos = [...new Set(ledgers.accurate.map(r => r.mo))].filter(Boolean);

    return (
      <div className="tab-pane active" style={{padding: '20px'}}>
        <div className="flow-controls">
          <div className="field-group" style={{minWidth: '300px'}}>
            <label className="field-label">Filter Topology by MO</label>
            <select className="field-input" value={flowFilterMo} onChange={(e) => setFlowFilterMo(e.target.value)}>
              <option value="">-- All MOs (Sum of Variants) --</option>
              {allMos.map(mo => <option key={mo} value={mo}>{mo}</option>)}
            </select>
          </div>
        </div>

        <div className="visual-flow-container">
          <svg className="flow-svg-overlay">
            <path d="M 300 240 L 380 240" />
            <path d="M 580 240 L 630 240 L 630 100 L 680 100" />
            <path d="M 580 240 L 680 240" />
            <path d="M 580 240 L 630 240 L 630 380 L 680 380" />
            <path d="M 580 240 L 610 240 L 610 520 L 680 520" />
            <path d="M 580 240 L 590 240 L 590 660 L 680 660" />
          </svg>

          <div className="flow-nodes-wrapper">
            {Object.entries(nodes).map(([key, node]) => (
              <div key={key} className={`flow-node node-${key} ${node.color}`} onClick={() => setSelectedFlowNode({ key, data: node })}>
                <div className="node-title">{node.title}</div>
                <div className="node-stats">
                  <div className="stat-item">
                    <span className="stat-label">Total IN</span>
                    <span className="stat-val stat-val-in">{node.in}</span>
                  </div>
                  <div className="stat-item" style={{alignItems: 'flex-end'}}>
                    <span className="stat-label">Total OUT</span>
                    <span className="stat-val stat-val-out">{node.out}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {selectedFlowNode && (
            <>
              <div className="modal-backdrop" onClick={() => setSelectedFlowNode(null)}></div>
              <div className="node-detail-modal">
                <h3 style={{marginTop: 0, color: 'var(--ac-navy)'}}>{selectedFlowNode.data.title} - Tracking Details</h3>
                <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '10px'}}>
                  <p style={{margin: 0}}><strong>Total Incoming:</strong> <span style={{color: 'var(--ac-blue-dark)', fontSize: '18px', fontWeight: 'bold'}}>{selectedFlowNode.data.in}</span></p>
                  <p style={{margin: 0}}><strong>Total Outgoing:</strong> <span style={{color: 'var(--ac-amber-dark)', fontSize: '18px', fontWeight: 'bold'}}>{selectedFlowNode.data.out}</span></p>
                </div>
                <hr style={{borderColor: 'var(--ac-border)', margin: '15px 0'}}/>
                <p style={{fontSize: '13px', color: 'var(--ac-text-faint)'}}>
                  Aggregated flow breakdown for tracking in this station based on MO <b>{flowFilterMo || "ALL MOs"}</b>. Summing variants concurrently.
                </p>
                <button className="tab-pill tab-pill-active" onClick={() => setSelectedFlowNode(null)} style={{width: '100%', marginTop: '15px', padding: '12px'}}>Close Details</button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  };
 
  return (
    <div className="afterchannel-container">
      <div className="ac-header">
        <h2 className="ac-title">Afterchannel Ledger</h2>
        <div className="tab-buttons">
          <button className={`tab-pill tab-pill-accurate ${activeTab === 'accurate' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('accurate')}>Accurate</button>
          <button className={`tab-pill tab-pill-cps ${activeTab === 'cps' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('cps')}>CPS</button>
          <button className={`tab-pill tab-pill-rework ${activeTab === 'rework' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('rework')}>Rework</button>
          <button className={`tab-pill tab-pill-dismantling ${activeTab === 'dismantling' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('dismantling')}>Dismantling</button>
          <button className={`tab-pill tab-pill-autopackaging ${activeTab === 'autopackaging' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('autopackaging')}>Autopackaging</button>
          <button className={`tab-pill tab-pill-fps ${activeTab === 'fps' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('fps')}>FPS</button>
          
          <div style={{width: '1px', height: '24px', background: 'rgba(255,255,255,0.3)', margin: '0 8px'}}></div>
          
          <button className={`tab-pill ${activeTab === 'summary' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('summary')}>Summary</button>
          
          {/* THE NEW VISUAL FLOW BUTTON */}
          <button className={`tab-pill ${activeTab === 'visualFlow' ? 'tab-pill-active' : ''}`} onClick={() => setActiveTab('visualFlow')}>Visual Flow</button>
        </div>
      </div>

      {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].includes(activeTab) && (
        <div className="filter-card">
           <p style={{fontStyle: 'italic', color: 'var(--ac-text-faint)'}}>Standard forms continue here as normally structured in your component tree.</p>
        </div>
      )}

      {activeTab === 'summary' && (
        <div className="tab-pane active" style={{padding: '20px'}}>
          <div style={{marginBottom: '15px'}}>
            <input type="text" placeholder="Search MO in Summary..." className="field-input" value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{maxWidth: '300px'}} />
          </div>
          <div style={{overflowX: 'auto', background: '#fff', borderRadius: '12px', border: '1px solid var(--ac-border)'}}>
            <table className="summary-table">
                <thead>
                  <tr>
                    <th>MO NUMBER / VARIANT</th>
                    <th colSpan="2">REWORK</th>
                    <th colSpan="2">DISMANTLING</th>
                    <th colSpan="2">CPS</th>
                    <th colSpan="2">ACCURATE</th>
                    <th colSpan="2">AUTOPACKAGING</th>
                    <th>FPS</th>
                  </tr>
                  <tr>
                    <th></th>
                    <th>IN</th><th>OUT</th>
                    <th>IN</th><th>OUT</th>
                    <th>IN</th><th>OUT</th>
                    <th>IN</th><th>OUT</th>
                    <th>IN</th><th>OUT</th>
                    <th>IN</th>
                  </tr>
                </thead>
                <tbody>
                  {generateSummaryData().map((moData) => (
                    <React.Fragment key={moData.mo}>
                      <tr style={{background: '#eaf0fd', fontWeight: 'bold', cursor: 'pointer'}} onClick={() => setExpandedMOs(prev => ({...prev, [moData.mo]: !prev[moData.mo]}))}>
                        <td className="label-cell">{moData.mo} {expandedMOs[moData.mo] ? '▼' : '▶'}</td>
                        <td colSpan="11">Click to {expandedMOs[moData.mo] ? 'collapse' : 'expand'} variants</td>
                      </tr>
                      {expandedMOs[moData.mo] && Object.entries(moData.variants).map(([vKey, vData]) => {
                        const rowId = `${moData.mo}-${vKey}`;
                        return (
                          <React.Fragment key={rowId}>
                            <tr>
                              <td className="label-cell" style={{paddingLeft: '30px', color: 'var(--ac-blue)'}} onClick={() => setExpandedVariants(prev => ({...prev, [rowId]: !prev[rowId]}))} style={{cursor: 'pointer'}}>
                                {vKey} {expandedVariants[rowId] ? '▼' : '▶'}
                              </td>
                              <td>{vData.rwIn || '-'}</td><td>{vData.rwOut || '-'}</td>
                              <td>{vData.disIn || '-'}</td><td className="cell-dis-out">{vData.disOut || '-'}</td>
                              <td>{vData.cpsIn || '-'}</td><td>{vData.cpsOut || '-'}</td>
                              <td>{vData.accIn || '-'}</td><td>{vData.accOut || '-'}</td>
                              <td>{vData.apIn || '-'}</td><td>{vData.apOut || '-'}</td>
                              <td>{vData.fpsIn || '-'}</td>
                            </tr>
                            {expandedVariants[rowId] && (
                              <tr><td colSpan="12" style={{padding: 0}}>{renderMoDispatchDetails(vData.records)}</td></tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                      {expandedMOs[moData.mo] && (
                        <tr className="row-total">
                          <td className="label-cell">TOTAL FOR {moData.mo}:</td>
                          <td>{moData.totals.rwIn || '-'}</td><td>{moData.totals.rwOut || '-'}</td>
                          <td>{moData.totals.disIn || '-'}</td><td className="cell-dis-out">{moData.totals.disOut || '-'}</td>
                          <td>{moData.totals.cpsIn || '-'}</td><td>{moData.totals.cpsOut || '-'}</td>
                          <td>{moData.totals.accIn || '-'}</td><td>{moData.totals.accOut || '-'}</td>
                          <td>{moData.totals.apIn || '-'}</td><td>{moData.totals.apOut || '-'}</td>
                          <td>{moData.totals.fpsIn || '-'}</td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
            </table>
          </div>
        </div>
      )}

      {/* RENDER THE NEW VISUAL FLOW */}
      {activeTab === 'visualFlow' && renderVisualFlow()}
      
    </div>
  );
};
 
export default Afterchannel;
