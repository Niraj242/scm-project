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

  // XA Scrap states
  const [scrapData, setScrapData] = useState({});
  const [expandedScrap, setExpandedScrap] = useState({});

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
    fetchScrapData();
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

  const fetchScrapData = async () => {
    try {
      const res = await fetch(`${API}/api/afterchannel/scrap_data`);
      const json = await res.json();
      if (json.status === 'success') {
        setScrapData(json.data || {});
      }
    } catch (err) {
      console.error("Scrap Sync Failure:", err);
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
 
  // Two-way cross filter engines (Master Data)
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
      
      let shoScrapTotal = 0;
      let channelScrapTotal = 0;
      let reasonBreakdown = {};

      Object.keys(scrapData).forEach(scrapMo => {
        if (scrapMo.startsWith(moData.mo)) {
           const codeMap = scrapData[scrapMo];
           Object.keys(codeMap).forEach(rc => {
             const qty = codeMap[rc];
             if(!reasonBreakdown[rc]) reasonBreakdown[rc] = 0;
             reasonBreakdown[rc] += qty;
             if(rc.startsWith('HT') || rc.startsWith('FODS')) {
                 shoScrapTotal += qty;
             } else {
                 channelScrapTotal += qty;
             }
           });
        }
      });
      
      moData.xaScrap = {
         sho: shoScrapTotal,
         channel: channelScrapTotal,
         total: shoScrapTotal + channelScrapTotal,
         reasons: reasonBreakdown
      };

      Object.values(moData.variants).forEach(vData => {
        vData.disOut = vData.disOutGeneral + Math.min(vData.irSentTot + vData.irScrap, vData.orSentTot + vData.orScrap);
      });
    });
 
    return Object.values(summaryMap).sort((a, b) => a.mo.localeCompare(b.mo));
  };
 
  const toggleMO = mo => setExpandedMOs(p => ({ ...p, [mo]: !p[mo] }));
  const toggleVariant = vKey => setExpandedVariants(p => ({ ...p, [vKey]: !p[vKey] }));
 
  const renderMoDispatchDetails = (records) => {
    const dispatches = records.filter(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.totalScrap > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0);
    if (dispatches.length === 0) return null;
    
    const grouped = {};
    dispatches.forEach(r => {
      const dept = r._dept;
      if (!grouped[dept]) grouped[dept] = [];
      grouped[dept].push(r);
    });
 
    return (
      <div className="details-container">
        {Object.entries(grouped).map(([dept, recs], idx) => (
          <div key={idx} style={{marginBottom: '15px'}}>
            <h5 className="details-title">{dept} Dispatches</h5>
            <div className="dispatch-events">
              {recs.map((r, i) => (
                <div key={i} className="dispatch-event">
                  {r.qty_sent > 0 && <div><strong className="qty-highlight">{r.qty_sent} PCS</strong> sent to <strong>{r.next_station || r.nextStation || 'N/A'}</strong></div>}
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
    const deptData = ledgers[deptKey] || [];
    if(deptData.length === 0) return <div className="ledger-empty-card">No records found in {deptName} Ledger.</div>;
    
    const filtered = deptData.filter(r => !ledgerSearchQuery || (r.mo && r.mo.toLowerCase().includes(ledgerSearchQuery.toLowerCase())) || (r.bearing_type && r.bearing_type.toLowerCase().includes(ledgerSearchQuery.toLowerCase())));
    if(filtered.length === 0) return <div className="ledger-empty-card">No records match your search.</div>;
    
    return (
      <div className="ledger-group">
        {filtered.sort((a,b)=>b.id-a.id).map(r => (
          <div key={r.id} className="ledger-card">
            <div className="ledger-card-header">
              <div>
                <h4 className="ledger-mo">{r.mo}</h4>
                <span className="ledger-variant">{r.bearing_type || r.type || r.item_type || r.item || 'N/A'}</span>
              </div>
              <div>
                <button onClick={() => handleEdit(r)} className="row-action-btn" title="Edit">✏️</button>
                <button onClick={() => handleDelete(r.id, deptKey)} className="row-action-btn delete-tint" title="Delete">🗑️</button>
              </div>
            </div>
            <div className="ledger-card-body">
              {r.qty_in > 0 && <div className="ledger-info-row"><span className="ledger-label">IN From {r.material_in_from || r.materialInFrom}:</span><span className="ledger-value val-in">{r.qty_in} PCS</span></div>}
              {r.qty_sent > 0 && <div className="ledger-info-row"><span className="ledger-label">OUT To {r.next_station || r.nextStation}:</span><span className="ledger-value val-out">{r.qty_sent} PCS</span></div>}
              {r.customer_order && <div className="ledger-info-row"><span className="ledger-label">Order:</span><span className="ledger-value">{r.customer_order}</span></div>}
              {deptKey === 'dismantling' && (
                <>
                  {(r.ir_sent>0||r.or_sent>0||r.cage_sent>0||r.roller_sent>0) && (
                    <div className="ledger-info-row" style={{flexDirection:'column', gap:'4px'}}>
                      <span className="ledger-label">Component Dispatches:</span>
                      {r.ir_sent>0 && <div>{r.ir_sent} IR ➔ {r.ir_station}</div>}
                      {r.or_sent>0 && <div>{r.or_sent} OR ➔ {r.or_station}</div>}
                      {r.cage_sent>0 && <div>{r.cage_sent} Cage ➔ {r.cage_station}</div>}
                      {r.roller_sent>0 && <div>{r.roller_sent} Roll/Ball ➔ {r.roller_station}</div>}
                    </div>
                  )}
                  {(r.ir_scrap>0||r.or_scrap>0||r.cage_scrap>0||r.ball_scrap>0||r.roller_scrap>0) && (
                    <div className="ledger-info-row"><span className="ledger-label">Scrap:</span><span className="val-scrap">{(r.ir_scrap||0)+(r.or_scrap||0)+(r.cage_scrap||0)+(r.ball_scrap||0)+(r.roller_scrap||0)} PCS 🚩</span></div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  };
 
  const renderPVSMFlow = () => {
    // 1. Triggered on button click
    const handleFlowSearch = () => {
      setIsFlowLoaded(true);
    };

    // 2. Filter Data based on selection
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
        return [];
      }
      return data;
    };

    const dataAccurate = getFiltered('accurate');
    const dataCps = getFiltered('cps');
    const dataRework = getFiltered('rework');
    const dataDismantling = getFiltered('dismantling');
    const dataAutopackaging = getFiltered('autopackaging');
    const dataFps = getFiltered('fps');

    // Strict Double Count Prevention for Accurate Net Logic
    const accIn = dataAccurate.reduce((sum, r) => {
      const from = String(r.material_in_from || r.materialInFrom || '').toLowerCase();
      if (!from.includes('rework') && !from.includes('dismantling') && !from.includes('vibration')) {
        return sum + (Number(r.qty_in || 0));
      }
      return sum;
    }, 0);

    const accOut = dataAccurate.reduce((sum, r) => {
      const to = String(r.next_station || r.nextStation || '').toLowerCase();
      if (!to.includes('autopackaging')) {
        return sum + (Number(r.qty_sent || 0));
      }
      return sum;
    }, 0);

    const sumSimple = (arr, key1, key2) => arr.reduce((s, r) => s + (Number(r[key1] || r[key2] || 0)), 0);
    
    // Dismantling Specifics
    const disInTot = sumSimple(dataDismantling, 'qty_in', 'qtyIn');
    const disOutGen = sumSimple(dataDismantling, 'qty_sent', 'qtySent');
    const disIrScrap = sumSimple(dataDismantling, 'ir_scrap', 'irScrap');
    const disOrScrap = sumSimple(dataDismantling, 'or_scrap', 'orScrap');
    
    const disIrSent = sumSimple(dataDismantling, 'ir_sent', 'irSent');
    const disOrSent = sumSimple(dataDismantling, 'or_sent', 'orSent');
    
    const disOutComp = Math.min(disIrSent + disIrScrap, disOrSent + disOrScrap);
    const disTotalOut = disOutGen + disOutComp;

    const totals = {
      dis: { in: disInTot, out: disTotalOut, visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
      cps: { in: sumSimple(dataCps, 'qty_in', 'qtyIn'), out: sumSimple(dataCps, 'qty_sent', 'qtySent'), visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
      rw: { in: sumSimple(dataRework, 'qty_in', 'qtyIn'), out: sumSimple(dataRework, 'qty_sent', 'qtySent'), visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
      acc: { in: accIn, out: accOut, visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
      ap: { in: sumSimple(dataAutopackaging, 'qty_in', 'qtyIn'), out: sumSimple(dataAutopackaging, 'qty_sent', 'qtySent'), visited: isFlowLoaded ? 'Visited' : 'Not Visited' },
      fps: { in: sumSimple(dataFps, 'qty_in', 'qtyIn'), out: sumSimple(dataFps, 'qty_sent', 'qtySent'), visited: isFlowLoaded ? 'Finished' : 'Not Visited' }
    };

    const NodeCard = ({ title, subtitle, icon, mIn, mOut, customMetrics, visited, borderCls }) => (
      <div className={`pvsm-card ${borderCls}`}>
        <div className="pvsm-card-header">
          <span className="pvsm-card-icon">{icon}</span>
          <div className="pvsm-card-title-area">
            <h4>{title}</h4>
            <span>{subtitle}</span>
          </div>
        </div>
        <div className="pvsm-card-metrics" style={{flexWrap: 'wrap'}}>
          {mIn !== undefined && (
            <div className="pvsm-metric">
              <span className="pvsm-metric-icon green">↓</span>
              <label>Incoming</label>
              <strong className="green">{mIn}</strong> <sub>PCS</sub>
            </div>
          )}
          {mOut !== undefined && (
            <div className="pvsm-metric">
              <span className="pvsm-metric-icon blue">↑</span>
              <label>Outgoing</label>
              <strong className="blue">{mOut}</strong> <sub>PCS</sub>
            </div>
          )}
          {/* Dynamically Map Custom Metrics (like the individual Scraps) */}
          {customMetrics && customMetrics.map((cm, i) => (
            <div key={i} className="pvsm-metric" style={{flexBasis: '40%'}}>
              <span className={`pvsm-metric-icon ${cm.color}`}>○</span>
              <label>{cm.label}</label>
              <strong className={cm.color}>{cm.val}</strong> <sub>PCS</sub>
            </div>
          ))}
        </div>
        <div className="pvsm-card-footer">
          <span className={`pvsm-badge ${visited === 'Visited' || visited === 'Finished' ? 'blue' : ''}`}>{visited}</span>
        </div>
      </div>
    );

    return (
      <div className="pvsm-flow-wrapper">
        <div className="filter-card" style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', marginBottom: '25px', padding: '15px 22px' }}>
          <div style={{ flex: 1 }}>
            <label className="field-label">Flow MO Number</label>
            <select className="field-input" value={pvsmMo} onChange={(e) => { setPvsmMo(e.target.value); setIsFlowLoaded(false); }}>
              <option>Select MO</option>
              {allUniqueMos.map(mo => <option key={mo}>{mo}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="field-label">Flow Variant</label>
            <select className="field-input" value={pvsmType} onChange={(e) => { setPvsmType(e.target.value); setIsFlowLoaded(false); }}>
              <option>Select Type</option>
              {allUniqueVariants.map(v => <option key={v}>{v}</option>)}
            </select>
          </div>
          <button className="submit-btn submit-btn-in" style={{ width: 'auto', marginTop: 0, padding: '12px 25px' }} onClick={handleFlowSearch}>
            Generate VSM
          </button>
        </div>

        <div className="pvsm-canvas-container">
          <svg className="pvsm-svg-overlay">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
              </marker>
              <marker id="arrow-dash" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
              </marker>
            </defs>
            {/* Top Row Connectors (DM -> SHO -> Disassembly -> CPS) */}
            <path d="M 160 65 L 173 65" markerEnd="url(#arrow)" />
            <path d="M 340 65 L 353 65" markerEnd="url(#arrow)" />
            <path d="M 520 65 L 533 65" markerEnd="url(#arrow)" />
            <path d="M 700 65 L 873 65" markerEnd="url(#arrow)" />
            
            {/* To CPS (Left-down) */}
            <path d="M 620 130 Q 620 180 980 180 L 980 155" markerEnd="url(#arrow)" />
            
            {/* Row 2 Connectors (Disassembly -> Rework -> Accurate -> Autopacking) */}
            <path d="M 700 225 L 713 225" markerEnd="url(#arrow)" className="dashed-arrow" />
            <path d="M 880 225 L 893 225" markerEnd="url(#arrow)" className="dashed-arrow" />
            <path d="M 1060 225 L 1073 225" markerEnd="url(#arrow)" />
            
            {/* Row 2 to Row 3 (Autopacking -> FPS) and (Disassembly -> Common Scrap) */}
            <path d="M 1160 290 Q 1160 330 980 330 L 980 315" markerEnd="url(#arrow)" />
            <path d="M 620 290 L 620 312" markerEnd="url(#arrow-dash)" className="dashed-arrow" />
          </svg>

          <div className="pvsm-grid">
            {/* ROW 1 */}
            <div className="node-pos-dmstore">
              <NodeCard title="DM Store" subtitle="Material Storage" icon="🏛" mIn={0} mOut={0} visited="Not Visited" borderCls="" />
            </div>
            <div className="node-pos-sho">
              <NodeCard title="SHO" subtitle="Shared Handling" icon="📈" mIn={0} mOut={0} visited="Not Visited" borderCls="" />
            </div>
            <div className="node-pos-disassembly">
              <NodeCard title="Disassembly" subtitle="Vibration Dept" icon="⚙️" mIn={totals.dis.in} mOut={totals.dis.out} visited={totals.dis.visited} borderCls="border-red" customMetrics={[{label: 'IR Scrap', val: disIrScrap, color: 'red'}, {label: 'OR Scrap', val: disOrScrap, color: 'orange'}]} />
            </div>
            <div className="node-pos-cps">
              <NodeCard title="CPS" subtitle="Washing / Insp" icon="💧" mIn={totals.cps.in} mOut={totals.cps.out} visited={totals.cps.visited} borderCls="border-purple" />
            </div>
            
            {/* ROW 2 */}
            <div className="node-pos-rework">
              <NodeCard title="Rework" subtitle="Correction Dept" icon="🔧" mIn={totals.rw.in} mOut={totals.rw.out} visited={totals.rw.visited} borderCls="border-amber" />
            </div>
            <div className="node-pos-accurate">
              <NodeCard title="Accurate" subtitle="Precision Checks" icon="🔬" mIn={totals.acc.in} mOut={totals.acc.out} visited={totals.acc.visited} borderCls="border-blue" />
            </div>
            <div className="node-pos-autopacking">
              <NodeCard title="Auto Packing" subtitle="End of Line" icon="📦" mIn={totals.ap.in} mOut={totals.ap.out} visited={totals.ap.visited} borderCls="border-green" />
            </div>

            {/* ROW 3 */}
            <div className="node-pos-common-scrap">
              <NodeCard title="Common Scrap" subtitle="Final Disposition" icon="🗑️" mIn={disIrScrap + disOrScrap} visited={disIrScrap + disOrScrap > 0 ? 'Visited' : 'Not Visited'} borderCls="" />
            </div>
            <div className="node-pos-fps">
              <NodeCard title="FPS" subtitle="Finished Goods" icon="🏁" mIn={totals.fps.in} mOut={totals.fps.out} visited={totals.fps.visited} borderCls="border-green" />
            </div>
          </div>
        </div>
      </div>
    );
  };
 
  return (
    <div className="afterchannel-container">
      <datalist id="depts-list">
        <option value="CPS" />
        <option value="Rework" />
        <option value="Accurate" />
        <option value="Autopackaging" />
        <option value="FPS" />
        <option value="Scrap" />
      </datalist>
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
              onClick={() => {
                setActiveTab(tab); 
                setEditingRecord(null); 
                setLedgerSearchQuery(''); 
                setBearingFamily(''); 
                resetComponentScrapStates();
              }}
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
              <label className="field-label">MO No.</label>
              <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." className="field-input" required />
            </div>
            <div className="field-group">
              <label className="field-label">Actual Production</label>
              <input type="text" value={`${actualProductionQty} PCS`} readOnly className="field-input field-input-readout" />
            </div>
          </div>
          <div className="mode-toggle-row">
            <button className={`mode-btn mode-btn-in ${entryMode === 'IN' ? 'mode-btn-active' : ''}`} onClick={() => setEntryMode('IN')}>Register IN</button>
            <button className={`mode-btn mode-btn-out ${entryMode === 'OUT' ? 'mode-btn-active' : ''}`} onClick={() => setEntryMode('OUT')}>Register OUT</button>
            <input type="text" placeholder={`Search ${activeTab.toUpperCase()} Ledger...`} className="field-input" style={{width: '250px', marginLeft: 'auto'}} value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} />
            {editingRecord && <button className="cancel-edit-btn" onClick={() => setEditingRecord(null)}>Cancel Edit</button>}
          </div>
        </div>
      )}
 
      <div className="ac-content">
        {activeTab !== 'summary' && activeTab !== 'dismantling' && activeTab !== 'visualFlow' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, activeTab)}>
              <fieldset className="form-fieldset">
                <div className="form-card-title">{activeTab.toUpperCase()} LOG ENTRY {editingRecord && `(Editing ID: ${editingRecord.id})`}</div>
                <div className="form-card-body">
                  <div className="form-grid-3">
                    {entryMode === 'IN' ? (
                      <>
                        <div className="field-group"><label className="field-label">In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                        <div className="field-group"><label className="field-label">Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} className="field-input" required><option></option><option>1</option><option>2</option><option>3</option></select></div>
                        <div className="field-group"><label className="field-label">In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} className="field-input" required/></div>
                        {activeTab === 'accurate' && <div className="field-group"><label className="field-label">PC No.</label><input type="text" name="pc" defaultValue={editingRecord?.pc_no || ''} className="field-input"/></div>}
                        {activeTab === 'rework' && <div className="field-group"><label className="field-label">Bearing Family</label><input type="text" name="bearingFamily" value={bearingFamily} onChange={e=>setBearingFamily(e.target.value)} className="field-input" required/></div>}
                        {activeTab === 'cps' && <div className="field-group"><label className="field-label">Item Type</label><select name="item" defaultValue={editingRecord?.item_type || ''} className="field-input" required><option></option><option>IR</option><option>OR</option><option>Assembly</option></select></div>}
                        {activeTab === 'cps' && <div className="field-group"><label className="field-label">RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} className="field-input"/></div>}
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
              <fieldset className="form-fieldset">
                <div className="form-card-title">DISMANTLING LOG ENTRY {editingRecord && `(Editing ID: ${editingRecord.id})`}</div>
                <div className="form-card-body">
                  <div className="form-grid-3">
                    <div className="field-group"><label className="field-label">In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input" required/></div>
                    <div className="field-group"><label className="field-label">Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} className="field-input" required><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div className="field-group"><label className="field-label">In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} className="field-input" required/></div>
                    <div className="field-group"><label className="field-label">Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} className="field-input" required/></div>
                    <div className="field-group"><label className="field-label">Bearing Family</label><input type="text" name="bearingFamily" value={bearingFamily} onChange={e=>setBearingFamily(e.target.value)} className="field-input" required/></div>
                  </div>
                  
                  <div className="component-dispatch-card">
                    <h4>Component Based Dispatches</h4>
                    <div className="component-row"><label>IR Component</label><div style={{display:'flex',gap:'10px'}}><input type="number" name="irSent" value={irSentVal} onChange={e=>setIrSentVal(e.target.value)} placeholder="Qty Sent" className="field-input" /><input type="text" name="irStation" value={irStationVal} onChange={e=>setIrStationVal(e.target.value)} placeholder="Target Station" className="field-input" /></div></div>
                    <div className="component-row"><label>OR Component</label><div style={{display:'flex',gap:'10px'}}><input type="number" name="orSent" value={orSentVal} onChange={e=>setOrSentVal(e.target.value)} placeholder="Qty Sent" className="field-input" /><input type="text" name="orStation" value={orStationVal} onChange={e=>setOrStationVal(e.target.value)} placeholder="Target Station" className="field-input" /></div></div>
                    <div className="component-row"><label>Cage Component</label><div style={{display:'flex',gap:'10px'}}><input type="number" name="cageSent" value={cageSentVal} onChange={e=>setCageSentVal(e.target.value)} placeholder="Qty Sent" className="field-input" /><input type="text" name="cageStation" value={cageStationVal} onChange={e=>setCageStationVal(e.target.value)} placeholder="Target Station" className="field-input" /></div></div>
                    <div className="component-row"><label>Roller/Ball Component</label><div style={{display:'flex',gap:'10px'}}><input type="number" name="rollerSent" value={rollerSentVal} onChange={e=>setRollerSentVal(e.target.value)} placeholder="Qty Sent" className="field-input" /><input type="text" name="rollerStation" value={rollerStationVal} onChange={e=>setRollerStationVal(e.target.value)} placeholder="Target Station" className="field-input" /></div></div>
                  </div>
 
                  <div className="scrap-entry-card">
                    <h4>Scrap Entry</h4>
                    <div className="scrap-grid-4">
                      <div><label>IR Scrap</label><input type="number" name="irScrap" value={irScrapVal} onChange={e=>setIrScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>OR Scrap</label><input type="number" name="orScrap" value={orScrapVal} onChange={e=>setOrScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>Cage Scrap</label><input type="number" name="cageScrap" value={cageScrapVal} onChange={e=>setCageScrapVal(e.target.value)} className="field-input" /></div>
                      <div><label>Ball/Roll Scrap</label><input type="number" name="ballScrap" value={ballScrapVal} onChange={e=>setBallScrapVal(e.target.value)} className="field-input" /></div>
                    </div>
                  </div>
 
                  <div className="form-grid-3">
                    <div className="field-group"><label className="field-label">Overall Qty Sent (Optional)</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} className="field-input"/></div>
                    <div className="field-group"><label className="field-label">Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} className="field-input"/></div>
                    <div className="field-group"><label className="field-label">Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} className="field-input"/></div>
                    <div className="field-group"><label className="field-label">Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} className="field-input"><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div className="field-group" style={{gridColumn: 'span 2'}}><label className="field-label">Remarks</label><input type="text" name="remark" value={remarkVal} onChange={e=>setRemarkVal(e.target.value)} placeholder="Optional defect details..." className="field-input"/></div>
                  </div>
                </div>
              </fieldset>
              <button type="submit" className="submit-btn submit-btn-in">{editingRecord ? 'Update Entry' : 'Save Dismantling Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'DISMANTLING')}
          </div>
        )}
 
        {activeTab === 'summary' && (
          <div className="summary-view card">
            <div className="summary-view-header">
              <h2 className="summary-view-title">End-to-End Tracking Summary</h2>
            </div>
            <div className="table-responsive">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th rowSpan="2">MO / Variant</th>
                    <th colSpan="2">Rework</th>
                    <th colSpan="2">Dismantling</th>
                    <th colSpan="2">CPS</th>
                    <th colSpan="2">Accurate</th>
                    <th colSpan="2">Autopkg</th>
                    <th>FPS</th>
                    <th colSpan="3" style={{backgroundColor: 'var(--ac-red-soft)', color: 'var(--ac-red)'}}>XA Scrap</th>
                  </tr>
                  <tr>
                    <th>In</th><th>Out</th><th>In</th><th>Out</th><th>In</th><th>Out</th>
                    <th>In</th><th>Out</th><th>In</th><th>Out</th><th>In</th>
                    <th style={{backgroundColor: 'var(--ac-red-soft)'}}>SHO</th>
                    <th style={{backgroundColor: 'var(--ac-red-soft)'}}>Channel</th>
                    <th style={{backgroundColor: 'var(--ac-red-soft)'}}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {generateSummaryData().map((moData) => (
                    <React.Fragment key={moData.mo}>
                      <tr className="row-mo" onClick={() => toggleMO(moData.mo)}>
                        <td className="mo-title">
                          <span className="expand-icon">{expandedMOs[moData.mo] ? '▼' : '▶'}</span> {moData.mo}
                        </td>
                        <td colSpan="11" style={{background: 'transparent'}}></td>
                        <td colSpan="3" style={{background: 'var(--ac-red-soft)'}}></td>
                      </tr>
                      
                      {expandedMOs[moData.mo] && Object.values(moData.variants).map((vData, i) => {
                        const vKey = `${moData.mo}-${vData.type}`;
                        return (
                          <React.Fragment key={i}>
                            <tr className="row-variant">
                              <td className="variant-title" onClick={() => toggleVariant(vKey)} style={{cursor: 'pointer', paddingLeft: '20px'}}>
                                <span className="expand-icon">{expandedVariants[vKey] ? '▼' : '▶'}</span> {vData.type}
                              </td>
                              <td>{vData.rwIn || '-'}</td><td>{vData.rwOut || '-'}</td>
                              <td>{vData.disIn || '-'}</td><td className="cell-dis-out">{vData.disOut || '-'}</td>
                              <td>{vData.cpsIn || '-'}</td><td>{vData.cpsOut || '-'}</td>
                              <td>{vData.accIn || '-'}</td><td>{vData.accOut || '-'}</td>
                              <td>{vData.apIn || '-'}</td><td>{vData.apOut || '-'}</td>
                              <td>{vData.fpsIn || '-'}</td>
                              <td colSpan="3" style={{background: 'var(--ac-surface-alt)'}}>-</td>
                            </tr>
                            {expandedVariants[vKey] && vData.records && vData.records.some(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.totalScrap > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0) && (
                               <tr className="row-details">
                                 <td colSpan="15" style={{padding: 0}}>
                                   {renderMoDispatchDetails(vData.records)}
                                 </td>
                               </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
 
                      {expandedMOs[moData.mo] && (
                        <>
                        <tr className="row-total">
                          <td className="label-cell">TOTAL FOR {moData.mo}:</td>
                          <td>{moData.totals.rwIn || '-'}</td><td>{moData.totals.rwOut || '-'}</td>
                          <td>{moData.totals.disIn || '-'}</td><td className="cell-dis-out">{moData.totals.disOut || '-'}</td>
                          <td>{moData.totals.cpsIn || '-'}</td><td>{moData.totals.cpsOut || '-'}</td>
                          <td>{moData.totals.accIn || '-'}</td><td>{moData.totals.accOut || '-'}</td>
                          <td>{moData.totals.apIn || '-'}</td><td>{moData.totals.apOut || '-'}</td>
                          <td>{moData.totals.fpsIn || '-'}</td>
                          
                          <td style={{fontWeight:'700', color: 'var(--ac-red)'}}>{moData.xaScrap?.sho > 0 ? moData.xaScrap.sho : '-'}</td>
                          <td style={{fontWeight:'700', color: 'var(--ac-red)'}}>{moData.xaScrap?.channel > 0 ? moData.xaScrap.channel : '-'}</td>
                          <td 
                            className="scrap-grand-total-cell" 
                            style={{cursor: Object.keys(moData.xaScrap?.reasons || {}).length > 0 ? 'pointer' : 'default'}} 
                            title={Object.keys(moData.xaScrap?.reasons || {}).length > 0 ? "Click to view detailed Reason Codes" : ""}
                            onClick={() => {
                                if(Object.keys(moData.xaScrap?.reasons || {}).length > 0) {
                                    setExpandedScrap(prev => ({...prev, [moData.mo]: !prev[moData.mo]}))
                                }
                            }}
                          >
                            {moData.xaScrap?.total > 0 ? `${moData.xaScrap.total} (View ▼)` : '-'}
                          </td>
                        </tr>
                        
                        {expandedScrap[moData.mo] && Object.keys(moData.xaScrap?.reasons || {}).length > 0 && (
                          <tr className="row-scrap-breakdown">
                              <td colSpan="12" style={{textAlign: 'right', fontStyle: 'italic', color: 'var(--ac-text-muted)', paddingRight: '15px'}}>
                                  Reason Code Breakdown for {moData.mo} (Scrap Sheet):
                              </td>
                              <td colSpan="3" style={{padding: '0', backgroundColor: 'var(--ac-surface)'}}>
                                  <table style={{width: '100%', margin: '0', background: 'var(--ac-surface-alt)', border: '1px dashed var(--ac-red-strong)'}}>
                                      <tbody>
                                          {Object.entries(moData.xaScrap.reasons).map(([code, qty]) => (
                                              <tr key={code}>
                                                  <td style={{padding: '4px 8px', borderBottom: '1px solid var(--ac-border)', fontWeight: 'bold', fontSize: '11px', color: 'var(--ac-navy)'}}>{code}</td>
                                                  <td style={{padding: '4px 8px', borderBottom: '1px solid var(--ac-border)', color: 'var(--ac-red)', fontSize: '11px', textAlign: 'right'}}>{qty} pcs</td>
                                              </tr>
                                          ))}
                                      </tbody>
                                  </table>
                              </td>
                          </tr>
                        )}
                        </>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ================= NEW P-VSM VISUAL FLOW ================= */}
        {activeTab === 'visualFlow' && renderPVSMFlow()}
      </div>
    </div>
  );
};
 
export default Afterchannel;
