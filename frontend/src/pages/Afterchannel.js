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

  // --- CORE SUMMARY HIERARCHY LOGIC ---
  const createEmptyFlowObject = () => ({
    accIn: 0, accOut: 0, cpsIn: 0, cpsOut: 0, rwIn: 0, rwOut: 0,
    disIn: 0, disOut: 0, apIn: 0, apOut: 0, fpsIn: 0, 
    irScrap: 0, orScrap: 0, cageScrap: 0, ballScrap: 0, totalScrap: 0, records: [],
    irSentTot: 0, orSentTot: 0, disOutGeneral: 0
  });

  const addFlowCounts = (node, r) => {
    const dept = r._dept;
    if (dept === 'accurate') { if (r.qty_in) node.accIn += Number(r.qty_in); if (r.qty_sent) node.accOut += Number(r.qty_sent); }
    else if (dept === 'cps') { if (r.qty_in) node.cpsIn += Number(r.qty_in); if (r.qty_sent) node.cpsOut += Number(r.qty_sent); }
    else if (dept === 'rework') { if (r.qty_in) node.rwIn += Number(r.qty_in); if (r.qty_sent) node.rwOut += Number(r.qty_sent); }
    else if (dept === 'dismantling') {
        if (r.qty_in) node.disIn += Number(r.qty_in);
        
        // Track the general overall amount, and individual IR/OR amounts separately for the "Lower Quantity" calculation
        if (r.qty_sent) node.disOutGeneral += Number(r.qty_sent);
        if (r.ir_sent) node.irSentTot += Number(r.ir_sent);
        if (r.or_sent) node.orSentTot += Number(r.or_sent);

        node.irScrap += (Number(r.ir_scrap) || 0); node.orScrap += (Number(r.or_scrap) || 0);
        node.cageScrap += (Number(r.cage_scrap) || 0); node.ballScrap += (Number(r.ball_scrap) || 0) + (Number(r.roller_scrap) || 0);
        node.totalScrap = node.irScrap + node.orScrap + node.cageScrap + node.ballScrap;
    }
    else if (dept === 'autopackaging') { if (r.qty_in) node.apIn += Number(r.qty_in); if (r.qty_sent) node.apOut += Number(r.qty_sent); }
    else if (dept === 'fps') { if (r.qty_in) node.fpsIn += Number(r.qty_in); } // FPS Out logic removed entirely
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

    // Post-calculation: Make Dismantling OUT purely equal to the lower count of (Total IR Sent+Scrap vs Total OR Sent+Scrap) + general OUT.
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
    if (outRecs.length === 0) return <div style={{padding: '10px', color: '#64748b', fontStyle: 'italic'}}>No dispatch/scrap events recorded here yet.</div>;
    const grouped = outRecs.reduce((acc, curr) => { if(!acc[curr._dept]) acc[curr._dept] = []; acc[curr._dept].push(curr); return acc; }, {});

    return (
      <div style={{display: 'flex', gap: '20px', flexWrap: 'wrap', padding: '15px', background: '#f8fafc', borderBottom: '2px solid #cbd5e1', boxShadow: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)'}}>
        {Object.keys(grouped).map(dept => (
          <div key={dept} style={{flex: '1 1 250px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px'}}>
            <h4 style={{margin: '0 0 10px 0', color: '#0f172a', borderBottom: '1px solid #e2e8f0', paddingBottom: '5px', textTransform:'uppercase', fontSize:'13px'}}>{dept} Activity</h4>
            <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
              {grouped[dept].map((r, i) => (
                <div key={i} style={{fontSize: '0.85em', background: '#f1f5f9', padding: '8px', borderRadius: '4px'}}>
                  {r.qty_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.qty_sent}</strong> sent to <strong>{r.next_station || 'N/A'}</strong></div>}
                  {r.ir_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.ir_sent} IR</strong> sent to <strong>{r.ir_station || 'N/A'}</strong></div>}
                  {r.or_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.or_sent} OR</strong> sent to <strong>{r.or_station || 'N/A'}</strong></div>}
                  {r.cage_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.cage_sent} Cage</strong> sent to <strong>{r.cage_station || 'N/A'}</strong></div>}
                  {r.roller_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.roller_sent} Roller/Ball</strong> sent to <strong>{r.roller_station || 'N/A'}</strong></div>}
                  {(r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0) && (
                      <div style={{color: '#dc2626', marginTop: '4px'}}>
                          Scrap: {[r.ir_scrap && `${r.ir_scrap} IR`, r.or_scrap && `${r.or_scrap} OR`, r.cage_scrap && `${r.cage_scrap} Cage`, (r.ball_scrap||r.roller_scrap) && `${r.ball_scrap||r.roller_scrap} Ball/Rollers`].filter(Boolean).join(', ')}
                      </div>
                  )}
                  <span style={{color: '#64748b'}}>On: {r.out_date || r.outDate} | Shift: {r.shift_out}</span>
                  {r.remark && <div style={{color: '#b45309', marginTop: '4px', fontStyle: 'italic'}}>"{r.remark}"</div>}
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
      const moMatch = (l.mo || '').toUpperCase().includes(search);
      const typeMatch = (l.bearing_type || l.type || l.item_type || '').toUpperCase().includes(search);
      return moMatch || typeMatch;
    });

    if (records.length === 0) return (
      <div style={{marginTop: '30px', padding: '20px', textAlign: 'center', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b'}}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px'}}>
          <span style={{fontWeight: 'bold', color: '#0f172a', fontSize: '1.2em'}}>{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '8px 12px', border: '1px solid #cbd5e1', borderRadius: '4px', width: '300px'}} />
        </div>
        No entries found.
      </div>
    );

    return (
      <div style={{marginTop: '30px', background: '#fff', borderRadius: '8px', border: '1px solid #cbd5e1', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'}}>
        <div style={{background: '#0f172a', padding: '15px 20px', color: '#fff', fontWeight: 'bold', fontSize: '1.2em', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <span>{deptName} - Global Entry Log</span>
          <input type="text" placeholder="Search MO or Variant..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '8px 12px', border: '1px solid #cbd5e1', borderRadius: '4px', width: '300px', outline: 'none', color: '#000'}} />
        </div>
        <div style={{overflowX: 'auto'}}>
          <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95em'}}>
            <thead>
              <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>MO</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Variant</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Material From</th>
                <th style={{padding: '12px 15px', color: '#1d4ed8', borderRight: '2px solid #cbd5e1', background: '#eff6ff'}}>Qty IN</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Date OUT</th>
                <th style={{padding: '12px 15px', color: '#475569', borderRight: '1px solid #e2e8f0'}}>Next Station</th>
                <th style={{padding: '12px 15px', color: '#b45309', background: '#fffbeb', borderRight: '1px solid #e2e8f0'}}>Qty OUT</th>
                <th style={{padding: '12px 15px', color: '#475569'}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const isScrap = isScrapStation(r.next_station || r.nextStation);
                return (
                  <tr key={i} style={{borderBottom: '1px solid #e2e8f0', background: i % 2 === 0 ? '#fff' : '#f8fafc', transition: 'background 0.2s'}} onMouseEnter={(e) => e.currentTarget.style.background = '#e2e8f0'} onMouseLeave={(e) => e.currentTarget.style.background = i % 2 === 0 ? '#fff' : '#f8fafc'}>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.mo || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold'}}>{r.bearing_type || r.type || r.item_type || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.in_date || r.inDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.material_in_from || r.materialInFrom || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '2px solid #cbd5e1', fontWeight: 'bold', color: '#1d4ed8', background: '#eff6ff'}}>{r.qty_in || r.qtyIn || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0'}}>{r.out_date || r.outDate || '-'}</td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', color: isScrap ? '#dc2626' : '#334155', fontWeight: isScrap ? 'bold' : 'normal'}}>
                      {r.next_station || r.nextStation || '-'}
                      {isScrap && <span style={{marginLeft: '5px', fontSize: '0.8em'}}>⚠️</span>}
                    </td>
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold', color: '#b45309', background: '#fffbeb'}}>{r.qty_sent || r.qtySent || r.ir_sent || '-'}</td>
                    <td style={{padding: '12px 15px'}}>
                      <button type="button" onClick={() => handleEdit(r)} style={{marginRight: '8px', cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Edit">✏️</button>
                      <button type="button" onClick={() => handleDelete(r.id, deptKey)} style={{cursor: 'pointer', border: 'none', background: 'none', fontSize: '1.2em'}} title="Delete">🗑️</button>
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

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      {/* Added "Channel" to the depts-list so it works across all Next Station inputs */}
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
      
      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily(''); resetComponentScrapStates();}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>{tab.toUpperCase()}</button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>📊 SUMMARY</button>
        </div>
      </div>

      {activeTab !== 'summary' && (
        <div style={{marginBottom: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
          <div style={{display: 'flex', gap: '20px'}}>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Variant</label>
              <input list="variants-list" value={selectedVariant} onChange={handleVariantChange} placeholder="Select or Type Variant..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>MO Number</label>
              <input list="mo-list" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} placeholder="Select or Type MO..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Target Production Qty</label>
              <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', color: '#16a34a'}} />
            </div>
          </div>
          <div style={{display: 'flex', gap: '20px', marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #cbd5e1'}}>
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📥 LOG IN (Receiving)</button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📤 LOG OUT (Dispatch)</button>
            {editingRecord && <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); setBearingFamily(''); resetComponentScrapStates(); }} style={{padding: '8px 20px', background: '#64748b', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', marginLeft: 'auto'}}>Cancel Edit</button>}
          </div>
        </div>
      )}

      <div className="ac-content">
        {['accurate', 'cps', 'rework', 'autopackaging', 'fps'].includes(activeTab) && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, activeTab)}>
              <fieldset style={{border: `1px solid ${entryMode==='IN'?'#cbd5e1':'#ea580c'}`, padding: '15px', borderRadius: '6px'}}>
                <legend style={{fontWeight: 'bold', color: entryMode==='IN'?'#000':'#ea580c'}}>{activeTab.toUpperCase()} - {entryMode==='IN' ? 'Receiving Log' : 'Dispatch Log'}</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    {entryMode === 'IN' ? (
                      <>
                        {activeTab === 'cps' && <div><label>Item</label><select name="item" defaultValue={editingRecord?.item_type || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>}
                        <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                        {activeTab === 'cps' && <div><label>RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} style={{width:'100%', padding:'6px'}}/></div>}
                        {activeTab === 'accurate' && <div><label>PC No</label><input type="text" name="pc" defaultValue={editingRecord?.pc_no || ''} style={{width:'100%', padding:'6px'}}/></div>}
                        <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                        {activeTab === 'cps' && <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>}
                        <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                      </>
                    ) : (
                      <>
                        {activeTab === 'fps' ? (
                          <div><label>Customer Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        ) : (
                          <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                        )}
                        <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                      </>
                    )}
                </div>
              </fieldset>
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger(activeTab, activeTab.toUpperCase())}
          </div>
        )}

        {/* ================= DISMANTLING TAB (MULTI-DISPATCH FEATURE) ================= */}
        {activeTab === 'dismantling' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              <div style={{marginBottom: '15px', padding: '12px', background: '#f1f5f9', borderRadius: '6px', border: '1px solid #cbd5e1', display: 'flex', gap: '10px'}}>
                <label style={{fontWeight: 'bold'}}>Bearing Family:</label>
                <select name="bearingFamily" value={bearingFamily} onChange={(e) => setBearingFamily(e.target.value)} style={{padding: '6px'}} required><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select>
              </div>

              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Dismantling - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px', background: '#fff7ed'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Dismantling - Dispatch Log</legend>
                  
                  {/* MULTI COMPONENT SPLITTER */}
                  <div style={{background: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #cbd5e1', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 12px 0', color: '#1e3a8a', borderBottom: '1px solid #e2e8f0', paddingBottom: '6px'}}>Specific Component Outbound Destinations</h4>
                    
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>IR Sent Qty</label><input type="number" name="irSent" value={irSentVal} onChange={e=>setIrSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>IR Next Station</label><input list="depts-list" name="irStation" value={irStationVal} onChange={e=>setIrStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>OR Sent Qty</label><input type="number" name="orSent" value={orSentVal} onChange={e=>setOrSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>OR Next Station</label><input list="depts-list" name="orStation" value={orStationVal} onChange={e=>setOrStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>Cage Sent Qty</label><input type="number" name="cageSent" value={cageSentVal} onChange={e=>setCageSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>Cage Next Station</label><input list="depts-list" name="cageStation" value={cageStationVal} onChange={e=>setCageStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Sent Qty</label><input type="number" name="rollerSent" value={rollerSentVal} onChange={e=>setRollerSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Next Station</label><input list="depts-list" name="rollerStation" value={rollerStationVal} onChange={e=>setRollerStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                  </div>

                  <div style={{background: '#f8fafc', padding: '15px', borderRadius: '6px', border: '1px dashed #ef4444', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 12px 0', color: '#dc2626'}}>Component Scrap Entry</h4>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px'}}>
                      <div><label style={{fontSize:'0.85em'}}>IR Scrap</label><input type="number" name="irScrap" value={irScrapVal} onChange={e=>setIrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>OR Scrap</label><input type="number" name="orScrap" value={orScrapVal} onChange={e=>setOrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>Cage Scrap</label><input type="number" name="cageScrap" value={cageScrapVal} onChange={e=>setCageScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>Ball/Roll Scrap</label><input type="number" name="ballScrap" value={ballScrapVal} onChange={e=>setBallScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                  </div>

                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Overall Qty Sent (Optional)</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent||''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Next Station (Overall)</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station||''} style={{width:'100%', padding:'6px'}}/></div>
                    <div style={{gridColumn: 'span 1'}}><label>Remarks</label><input type="text" name="remark" value={remarkVal} onChange={e=>setRemarkVal(e.target.value)} style={{width:'100%', padding:'6px'}} placeholder="General remarks..."/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date||''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out||''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Dismantling Processing')}
          </div>
        )}

        {/* ================= SUMMARY VIEW ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '25px', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', border: '1px solid #e2e8f0'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.4em', margin: 0, color: '#0f172a', fontWeight: 'bold'}}>MO Variant Flow Hierarchy</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '10px 15px', width: '350px', border: '2px solid #cbd5e1', borderRadius: '6px', outline: 'none'}} />
            </div>

            <div style={{overflowX: 'auto'}}>
              <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82em'}}>
                <thead>
                  <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', color: '#0f172a', minWidth: '180px'}}>Master Order / Variant</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rw IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rw OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>FPS IN</th>
                    {/* FPS OUT Removed as requested */}
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>IR Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>OR Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Cg Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Rl Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fca5a5'}}>Tot Scrp</th>
                  </tr>
                </thead>
                <tbody>
                  {generateSummaryData().map(moData => (
                    <React.Fragment key={moData.mo}>
                      {/* LEVEL 0: MO ROW */}
                      <tr onClick={() => setExpandedMOs(p => ({...p, [moData.mo]: !p[moData.mo]}))} style={{cursor: 'pointer', background: expandedMOs[moData.mo] ? '#e2e8f0' : '#f8fafc', fontWeight: 'bold', color: '#1e293b'}}>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{expandedMOs[moData.mo] ? '▼' : '▶'} {moData.mo}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.rwIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.rwOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.disIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px', color: '#1d4ed8'}}>{moData.totals.disOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.cpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.cpsOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.accIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.accOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.apIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.apOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.fpsIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.irScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.orScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.cageScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.ballScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fee2e2', color:'#b91c1c'}}>{moData.totals.totalScrap || '-'}</td>
                      </tr>

                      {expandedMOs[moData.mo] && Object.entries(moData.variants).map(([variant, vData]) => {
                        const vKey = `${moData.mo}-${variant}`;
                        return (
                          <React.Fragment key={variant}>
                            {/* LEVEL 1: VARIANT ROW */}
                            <tr onClick={() => setExpandedVariants(p => ({...p, [vKey]: !p[vKey]}))} style={{cursor: 'pointer', background: '#ffffff', color: '#334155'}}>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px 10px 10px 25px', borderLeft: '4px solid #3b82f6', fontWeight: 'bold'}}>{expandedVariants[vKey] ? '▼' : '▶'} {variant}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.rwIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.rwOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.disIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px', color: '#1d4ed8'}}>{vData.disOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.cpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.cpsOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.accIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.accOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.apIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.apOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.fpsIn || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.irScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.orScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.cageScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.ballScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fee2e2', color:'#b91c1c'}}>{vData.totalScrap || '-'}</td>
                            </tr>
                            
                            {/* LEVEL 2: COMPONENT DISPATCH DETAILS */}
                            {expandedVariants[vKey] && (
                              <tr><td colSpan="17" style={{border: '1px solid #cbd5e1', padding: 0}}>{renderMoDispatchDetails(vData.records)}</td></tr>
                            )}
                          </React.Fragment>
                        );
                      })}

                      {/* MO BOTTOM TOTAL ROW */}
                      {expandedMOs[moData.mo] && (
                        <tr style={{background: '#cbd5e1', fontWeight: 'bold', borderTop: '2px solid #64748b', color: '#0f172a'}}>
                          <td style={{border: '1px solid #94a3b8', padding: '10px', textAlign: 'right'}}>TOTAL FOR {moData.mo}:</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.rwIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.rwOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.disIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px', color: '#1d4ed8'}}>{moData.totals.disOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.cpsIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.cpsOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.accIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.accOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.apIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.apOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.fpsIn || '-'}</td>
                          <td colSpan="5" style={{border: '1px solid #94a3b8', padding: '10px', textAlign: 'center', background: '#fca5a5'}}>Grand Total Scrap: {moData.totals.totalScrap}</td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Afterchannel;
