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
  const [expandedMoRow, setExpandedMoRow] = useState(null); // Track clicked MO in summary

  const [formDate, setFormDate] = useState('');
  const [bearingFamily, setBearingFamily] = useState(''); 

  const [irScrapVal, setIrScrapVal] = useState('');
  const [orScrapVal, setOrScrapVal] = useState('');
  const [cageScrapVal, setCageScrapVal] = useState('');
  const [ballScrapVal, setBallScrapVal] = useState('');
  const [rollerScrapVal, setRollerScrapVal] = useState('');
  const [remarkVal, setRemarkVal] = useState('');
  const [customQtySent, setCustomQtySent] = useState('');

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
      'ballScrap', 'rollerScrap', 'cageScrap', 'irScrap', 'orScrap'
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
    setIrScrapVal('');
    setOrScrapVal('');
    setCageScrapVal('');
    setBallScrapVal('');
    setRollerScrapVal('');
    setRemarkVal('');
    setCustomQtySent('');
  };

  const handleEdit = (record) => {
    setMoNumber(record.mo || '');
    setSelectedVariant(record.type || record.bearing_type || '');
    setBearingFamily(record.bearing_family || record.bearingFamily || '');
    setEntryMode((record.qty_sent || record.qtySent) ? 'OUT' : 'IN');
    
    setIrScrapVal(record.ir_scrap ?? '');
    setOrScrapVal(record.or_scrap ?? '');
    setCageScrapVal(record.cage_scrap ?? '');
    setBallScrapVal(record.ball_scrap ?? '');
    setRollerScrapVal(record.roller_scrap ?? '');
    setRemarkVal(record.remark || '');
    setCustomQtySent(record.qty_sent || record.qtySent || '');

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

  const generateSummaryData = () => {
    const summaryMap = {};
    const allLists = [...ledgers.rework, ...ledgers.dismantling, ...ledgers.cps, ...ledgers.accurate, ...ledgers.autopackaging, ...ledgers.fps];
    
    allLists.forEach(item => {
      if (!item.mo) return;
      if (!summaryMap[item.mo]) {
        summaryMap[item.mo] = {
          mo: item.mo,
          rwIn: 0, rwOut: 0,
          disIn: 0, disOut: 0,
          cpsIn: 0, cpsOut: 0,
          accIn: 0, accOut: 0,
          apIn: 0, apOut: 0,
          fpsIn: 0, fpsOut: 0,
          irScrap: 0, orScrap: 0, cageScrap: 0, ballScrap: 0, totalScrap: 0
        };
      }
    });

    ledgers.rework.forEach(r => { if(r.qty_in) summaryMap[r.mo].rwIn += Number(r.qty_in); if(r.qty_sent) summaryMap[r.mo].rwOut += Number(r.qty_sent); });
    ledgers.dismantling.forEach(r => {
      if(r.qty_in) summaryMap[r.mo].disIn += Number(r.qty_in);
      if(r.qty_sent) summaryMap[r.mo].disOut += Number(r.qty_sent);
      summaryMap[r.mo].irScrap += (Number(r.ir_scrap) || 0);
      summaryMap[r.mo].orScrap += (Number(r.or_scrap) || 0);
      summaryMap[r.mo].cageScrap += (Number(r.cage_scrap) || 0);
      summaryMap[r.mo].ballScrap += (Number(r.ball_scrap) || 0) + (Number(r.roller_scrap) || 0);
    });
    ledgers.cps.forEach(r => { if(r.qty_in) summaryMap[r.mo].cpsIn += Number(r.qty_in); if(r.qty_sent) summaryMap[r.mo].cpsOut += Number(r.qty_sent); });
    ledgers.accurate.forEach(r => { if(r.qty_in) summaryMap[r.mo].accIn += Number(r.qty_in); if(r.qty_sent) summaryMap[r.mo].accOut += Number(r.qty_sent); });
    ledgers.autopackaging.forEach(r => { if(r.qty_in) summaryMap[r.mo].apIn += Number(r.qty_in); if(r.qty_sent) summaryMap[r.mo].apOut += Number(r.qty_sent); });
    ledgers.fps.forEach(r => { if(r.qty_in) summaryMap[r.mo].fpsIn += Number(r.qty_in); if(r.qty_sent) summaryMap[r.mo].fpsOut += Number(r.qty_sent); });

    Object.keys(summaryMap).forEach(key => {
      const s = summaryMap[key];
      s.totalScrap = s.irScrap + s.orScrap + s.cageScrap + s.ballScrap;
    });

    let result = Object.values(summaryMap);
    if (ledgerSearchQuery.trim()) {
      result = result.filter(item => item.mo.toLowerCase().includes(ledgerSearchQuery.toLowerCase()));
    }
    return result;
  };

  const filteredLedgerData = () => {
    if (activeTab === 'summary') return generateSummaryData();
    const list = ledgers[activeTab] || [];
    if (!ledgerSearchQuery.trim()) return list;
    return list.filter(item => (item.mo || '').toLowerCase().includes(ledgerSearchQuery.toLowerCase()));
  };

  const renderMoDispatchDetails = (mo) => {
    const allRecords = [
      ...ledgers.accurate.map(r => ({ ...r, sourceDept: 'Accurate' })),
      ...ledgers.cps.map(r => ({ ...r, sourceDept: 'CPS' })),
      ...ledgers.rework.map(r => ({ ...r, sourceDept: 'Rework' })),
      ...ledgers.dismantling.map(r => ({ ...r, sourceDept: 'Dismantling' })),
      ...ledgers.autopackaging.map(r => ({ ...r, sourceDept: 'Autopackaging' })),
      ...ledgers.fps.map(r => ({ ...r, sourceDept: 'FPS' }))
    ].filter(r => r.mo === mo && r.qty_sent > 0);

    if (allRecords.length === 0) return <div style={{padding: '10px', color: '#64748b'}}>No dispatch events recorded for this MO yet.</div>;

    const grouped = allRecords.reduce((acc, curr) => {
      if(!acc[curr.sourceDept]) acc[curr.sourceDept] = [];
      acc[curr.sourceDept].push(curr);
      return acc;
    }, {});

    return (
      <div style={{display: 'flex', gap: '20px', flexWrap: 'wrap', padding: '15px', background: '#f8fafc', borderBottom: '2px solid #cbd5e1', boxShadow: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)'}}>
        {Object.keys(grouped).map(dept => (
          <div key={dept} style={{flex: '1 1 300px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px'}}>
            <h4 style={{margin: '0 0 10px 0', color: '#0f172a', borderBottom: '1px solid #e2e8f0', paddingBottom: '5px'}}>{dept} Dispatches</h4>
            <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
              {grouped[dept].map((r, i) => (
                <div key={i} style={{fontSize: '0.85em', background: '#f1f5f9', padding: '8px', borderRadius: '4px'}}>
                  <strong style={{color: '#2563eb'}}>{r.qty_sent}</strong> sent to <strong>{r.next_station || 'N/A'}</strong> <br/>
                  <span style={{color: '#64748b'}}>On: {r.out_date || r.outDate} | Shift: {r.shift_out}</span>
                  {r.remark && <div style={{color: '#b45309', marginTop: '4px', fontStyle: 'italic'}}>{r.remark}</div>}
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
                    <td style={{padding: '12px 15px', borderRight: '1px solid #e2e8f0', fontWeight: 'bold', color: '#b45309', background: '#fffbeb'}}>{r.qty_sent || r.qtySent || '-'}</td>
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
      
      <datalist id="depts-list">
        <option value="Channel" /><option value="Accurate" /><option value="CPS" />
        <option value="Rework" /><option value="Dismantling" /><option value="Autopackaging" />
        <option value="FPS" /><option value="Scrap" />
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

      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => {setActiveTab(tab); setEditingRecord(null); setLedgerSearchQuery(''); setBearingFamily(''); resetComponentScrapStates();}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => {setActiveTab('summary'); setLedgerSearchQuery(''); setExpandedMoRow(null);}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>
            📊 SUMMARY
          </button>
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
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📥 LOG IN (Receiving)
            </button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📤 LOG OUT (Dispatch)
            </button>
            {editingRecord && (
              <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); setBearingFamily(''); resetComponentScrapStates(); }} style={{padding: '8px 20px', background: '#64748b', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', marginLeft: 'auto'}}>
                Cancel Edit
              </button>
            )}
          </div>
        </div>
      )}

      <div className="ac-content">
        
        {/* ================= ACCURATE TAB ================= */}
        {activeTab === 'accurate' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'accurate')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Accurate - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>PC No</label><input type="text" name="pc" defaultValue={editingRecord?.pc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Accurate - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('accurate', 'Accurate Processing')}
          </div>
        )}

        {/* ================= CPS TAB ================= */}
        {activeTab === 'cps' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'cps')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>CPS Assembly - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Item</label><select name="item" defaultValue={editingRecord?.item_type || ''} style={{width:'100%', padding:'6px'}}><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>RC No</label><input type="text" name="rcNo" defaultValue={editingRecord?.rc_no || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Channel</label><input list="channels-list" name="channel" defaultValue={editingRecord?.channel || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>CPS Assembly - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('cps', 'CPS Assembly')}
          </div>
        )}

        {/* ================= REWORK TAB ================= */}
        {activeTab === 'rework' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'rework')}>
              <div style={{marginBottom: '15px', padding: '12px', background: '#f1f5f9', borderRadius: '6px', border: '1px solid #cbd5e1', display: 'flex', alignItems: 'center', gap: '10px'}}>
                <label style={{fontWeight: 'bold', color: '#334155'}}>Bearing Family Specification:</label>
                <select name="bearingFamily" value={bearingFamily} onChange={(e) => setBearingFamily(e.target.value)} style={{padding: '6px', width: '200px', borderRadius: '4px', border: '1px solid #cbd5e1'}} required>
                  <option value=""></option>
                  <option value="DGBB">DGBB</option>
                  <option value="TRB">TRB</option>
                </select>
              </div>

              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Rework Station - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Rework Station - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('rework', 'Rework Station')}
          </div>
        )}

        {/* ================= DISMANTLING TAB ================= */}
        {activeTab === 'dismantling' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              <div style={{marginBottom: '15px', padding: '12px', background: '#f1f5f9', borderRadius: '6px', border: '1px solid #cbd5e1', display: 'flex', alignItems: 'center', gap: '10px'}}>
                <label style={{fontWeight: 'bold', color: '#334155'}}>Bearing Family Specification:</label>
                <select name="bearingFamily" value={bearingFamily} onChange={(e) => setBearingFamily(e.target.value)} style={{padding: '6px', width: '200px', borderRadius: '4px', border: '1px solid #cbd5e1'}} required>
                  <option value=""></option>
                  <option value="DGBB">DGBB</option>
                  <option value="TRB">TRB</option>
                </select>
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
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Dismantling - Dispatch & Component Scrap Entry</legend>
                  
                  <div style={{background: '#f8fafc', padding: '15px', borderRadius: '6px', border: '1px solid #cbd5e1', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 12px 0', color: '#0f172a', borderBottom: '1px solid #e2e8f0', paddingBottom: '6px'}}>Component Scrap Entry</h4>
                    
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px'}}>
                      <div>
                        <label style={{fontSize: '0.85em', fontWeight: '600', color:'#991b1b'}}>IR Scrap</label>
                        <input type="number" name="irScrap" value={irScrapVal} onChange={(e) => setIrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} placeholder="Pieces" />
                      </div>
                      <div>
                        <label style={{fontSize: '0.85em', fontWeight: '600', color:'#991b1b'}}>OR Scrap</label>
                        <input type="number" name="orScrap" value={orScrapVal} onChange={(e) => setOrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} placeholder="Pieces" />
                      </div>
                      <div>
                        <label style={{fontSize: '0.85em', fontWeight: '600', color:'#991b1b'}}>Cage Scrap</label>
                        <input type="number" name="cageScrap" value={cageScrapVal} onChange={(e) => setCageScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} placeholder="Pieces" />
                      </div>
                      {bearingFamily === 'TRB' ? (
                        <div>
                          <label style={{fontSize: '0.85em', fontWeight: '600', color:'#991b1b'}}>Roller Scrap</label>
                          <input type="number" name="rollerScrap" value={rollerScrapVal} onChange={(e) => setRollerScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} placeholder="Pieces" />
                        </div>
                      ) : (
                        <div>
                          <label style={{fontSize: '0.85em', fontWeight: '600', color:'#991b1b'}}>Ball Scrap</label>
                          <input type="number" name="ballScrap" value={ballScrapVal} onChange={(e) => setBallScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} placeholder="Pieces" />
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div>
                      <label>Overall Qty Sent</label>
                      <input type="number" name="qtySent" value={customQtySent} onChange={(e) => setCustomQtySent(e.target.value)} style={{width:'100%', padding:'6px'}} placeholder="e.g. 10 Rings" />
                    </div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div style={{gridColumn: 'span 2'}}><label>Remarks (e.g. 10 OR sent, 2 IR scrapped)</label><input type="text" name="remark" value={remarkVal} onChange={(e) => setRemarkVal(e.target.value)} style={{width:'100%', padding:'6px'}} placeholder="Write specific flow description here"/></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Dismantling Processing')}
          </div>
        )}

        {/* ================= AUTOPACKAGING TAB ================= */}
        {activeTab === 'autopackaging' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'autopackaging')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Autopackaging - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Autopackaging - Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('autopackaging', 'Autopackaging Station')}
          </div>
        )}

        {/* ================= FPS TAB ================= */}
        {activeTab === 'fps' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'fps')}>
              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>FPS - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>FPS - Final Dispatch Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Customer Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} onChange={(e) => setFormDate(e.target.value)} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('fps', 'FPS Storage')}
          </div>
        )}

        {/* ================= SUMMARY VIEW ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '25px', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', border: '1px solid #e2e8f0'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.4em', margin: 0, color: '#0f172a', fontWeight: 'bold'}}>Flow Distribution Summary</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '10px 15px', width: '350px', border: '2px solid #cbd5e1', borderRadius: '6px', outline: 'none'}} />
            </div>
            
            <p style={{fontStyle: 'italic', color: '#64748b', marginBottom: '15px'}}>💡 Click on any MO row to reveal the exact dispatch splits.</p>

            <div style={{overflowX: 'auto'}}>
              <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85em'}}>
                <thead>
                  <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', color: '#0f172a'}}>MO Number</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rework IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rework OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism. IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism. OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc. IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc. OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg. IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg. OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>FPS IN</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>FPS OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>IR Scrap</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>OR Scrap</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Cage Scrap</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Ball/Roll Scrap</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fca5a5', fontWeight:'bold'}}>Total Scrap</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLedgerData().map((row, index) => (
                    <React.Fragment key={index}>
                      <tr 
                        onClick={() => setExpandedMoRow(expandedMoRow === row.mo ? null : row.mo)} 
                        style={{cursor: 'pointer', background: expandedMoRow === row.mo ? '#eff6ff' : 'inherit', transition: 'background 0.2s'}}
                        onMouseEnter={(e) => {if(expandedMoRow !== row.mo) e.currentTarget.style.background = '#f8fafc'}} 
                        onMouseLeave={(e) => {if(expandedMoRow !== row.mo) e.currentTarget.style.background = 'inherit'}}
                      >
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', fontWeight: 'bold', color: '#2563eb'}}>
                          {expandedMoRow === row.mo ? '▼ ' : '▶ '} {row.mo}
                        </td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.rwIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.rwOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.disIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.disOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.cpsIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.cpsOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.accIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.accOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.apIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.apOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.fpsIn || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{row.fpsOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color: '#991b1b', fontWeight: row.irScrap ? 'bold' : 'normal'}}>{row.irScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color: '#991b1b', fontWeight: row.orScrap ? 'bold' : 'normal'}}>{row.orScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color: '#991b1b', fontWeight: row.cageScrap ? 'bold' : 'normal'}}>{row.cageScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color: '#991b1b', fontWeight: row.ballScrap ? 'bold' : 'normal'}}>{row.ballScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fee2e2', color: '#b91c1c', fontWeight:'bold'}}>{row.totalScrap || '-'}</td>
                      </tr>
                      {expandedMoRow === row.mo && (
                        <tr>
                          <td colSpan="18" style={{border: '1px solid #cbd5e1', padding: 0}}>
                            {renderMoDispatchDetails(row.mo)}
                          </td>
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
