/**
 * Strike Selection Page
 * Select optimal strikes from options chain
 */
import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type TabType = 'chain' | 'select' | 'compare';

export function StrikeSelectionPage() {
  const [activeTab, setActiveTab] = useState<TabType>('chain');
  const [ticker, setTicker] = useState('QQQ');
  const [expiration, setExpiration] = useState('30');
  
  const [chain] = useState({
    underlying: 450.0,
    calls: [
      { strike: 430, bid: 21.5, ask: 22.5, iv: 28, delta: -0.65, theta: -0.15, oi: 8500 },
      { strike: 440, bid: 14.2, ask: 15.0, iv: 26, delta: -0.48, theta: -0.12, oi: 12000 },
      { strike: 450, bid: 8.8, ask: 9.5, iv: 25, delta: -0.32, theta: -0.10, oi: 15000 },
      { strike: 460, bid: 4.5, ask: 5.0, iv: 26, delta: -0.18, theta: -0.08, oi: 11000 },
      { strike: 470, bid: 2.1, ask: 2.5, iv: 28, delta: -0.08, theta: -0.05, oi: 9000 },
    ],
    puts: [
      { strike: 430, bid: 2.0, ask: 2.5, iv: 27, delta: 0.08, theta: -0.05, oi: 7500 },
      { strike: 440, bid: 4.2, ask: 5.0, iv: 26, delta: 0.18, theta: -0.08, oi: 10000 },
      { strike: 450, bid: 8.5, ask: 9.5, iv: 25, delta: 0.32, theta: -0.10, oi: 14000 },
      { strike: 460, bid: 14.0, ask: 15.5, iv: 26, delta: 0.48, theta: -0.12, oi: 11000 },
      { strike: 470, bid: 21.0, ask: 23.0, iv: 28, delta: 0.65, theta: -0.15, oi: 8000 },
    ],
  });
  
  const [selectedStrategy, setSelectedStrategy] = useState('ATM');
  const [selectedType, setSelectedType] = useState('CALL');

  const strategies = [
    { id: 'ATM', name: 'At-The-Money', desc: 'Closest to current price' },
    { id: 'OTM', name: 'Out-The-Money', desc: '5% OTM for momentum' },
    { id: 'ITM', name: 'In-The-Money', desc: '10% ITM for safety' },
    { id: 'DELTA', name: 'Target Delta', desc: '30 delta target' },
    { id: 'RISK', name: 'Risk/Reward', desc: 'Best risk/reward ratio' },
    { id: 'IV', name: 'High IV', desc: 'Highest implied volatility' },
    { id: 'LIQ', name: 'Most Liquid', desc: 'Highest open interest' },
  ];

  const expirations = [
    { value: '7', label: '7 Days' },
    { value: '14', label: '14 Days' },
    { value: '21', label: '21 Days' },
    { value: '30', label: '30 Days' },
    { value: '45', label: '45 Days' },
    { value: '60', label: '60 Days' },
    { value: '90', label: '90 Days' },
  ];

  const formatPrice = (price: number) => `$${price.toFixed(2)}`;
  const formatPct = (pct: number) => `${pct.toFixed(1)}%`;

  return (
    <div className="w-full max-w-5xl mx-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Options Chain</h1>
        <div className="flex gap-2">
          <Select value={ticker} onValueChange={setTicker}>
            <SelectTrigger className="w-24">
              <SelectValue placeholder="Ticker" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="QQQ">QQQ</SelectItem>
              <SelectItem value="SPY">SPY</SelectItem>
              <SelectItem value="AAPL">AAPL</SelectItem>
              <SelectItem value="TSLA">TSLA</SelectItem>
              <SelectItem value="NVDA">NVDA</SelectItem>
            </SelectContent>
          </Select>
          <Select value={expiration} onValueChange={setExpiration}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {expirations.map(e => (
                <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('chain')}
          className={`px-4 py-2 rounded-lg font-medium ${
            activeTab === 'chain' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Chain
        </button>
        <button
          onClick={() => setActiveTab('select')}
          className={`px-4 py-2 rounded-lg font-medium ${
            activeTab === 'select' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Select Strike
        </button>
        <button
          onClick={() => setActiveTab('compare')}
          className={`px-4 py-2 rounded-lg font-medium ${
            activeTab === 'compare' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Compare
        </button>
      </div>

      {/* Chain Tab */}
      {activeTab === 'chain' && (
        <div className="space-y-4">
          <div className="flex gap-4 items-center text-gray-600 mb-2">
            <span>Underlying: {formatPrice(chain.underlying)}</span>
            <span>|</span>
            <span>Bid/Ask</span>
            <span>|</span>
            <span>IV</span>
            <span>|</span>
            <span>Delta</span>
            <span>|</span>
            <span>Theta</span>
            <span>|</span>
            <span>OI</span>
          </div>

          {/* Calls */}
          <Card>
            <CardHeader className="py-2">
              <CardTitle className="text-green-600">CALLS</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="text-gray-500 text-sm">
                    <th className="text-left p-2">Strike</th>
                    <th className="text-right p-2">Bid</th>
                    <th className="text-right p-2">Ask</th>
                    <th className="text-right p-2">IV</th>
                    <th className="text-right p-2">Delta</th>
                    <th className="text-right p-2">Theta</th>
                    <th className="text-right p-2">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {chain.calls.map((c, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="p-2 font-medium">${c.strike}</td>
                      <td className="p-2 text-right text-green-600">{formatPrice(c.bid)}</td>
                      <td className="p-2 text-right text-red-600">{formatPrice(c.ask)}</td>
                      <td className="p-2 text-right">{formatPct(c.iv)}</td>
                      <td className="p-2 text-right">{c.delta.toFixed(2)}</td>
                      <td className="p-2 text-right">{c.theta.toFixed(2)}</td>
                      <td className="p-2 text-right">{c.oi.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Puts */}
          <Card>
            <CardHeader className="py-2">
              <CardTitle className="text-red-600">PUTS</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="text-gray-500 text-sm">
                    <th className="text-left p-2">Strike</th>
                    <th className="text-right p-2">Bid</th>
                    <th className="text-right p-2">Ask</th>
                    <th className="text-right p-2">IV</th>
                    <th className="text-right p-2">Delta</th>
                    <th className="text-right p-2">Theta</th>
                    <th className="text-right p-2">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {chain.puts.map((p, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="p-2 font-medium">${p.strike}</td>
                      <td className="p-2 text-right text-green-600">{formatPrice(p.bid)}</td>
                      <td className="p-2 text-right text-red-600">{formatPrice(p.ask)}</td>
                      <td className="p-2 text-right">{formatPct(p.iv)}</td>
                      <td className="p-2 text-right">{p.delta.toFixed(2)}</td>
                      <td className="p-2 text-right">{p.theta.toFixed(2)}</td>
                      <td className="p-2 text-right">{p.oi.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Select Tab */}
      {activeTab === 'select' && (
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Strategy</CardTitle>
              <CardDescription>How to select the strike</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Select value={selectedStrategy} onValueChange={setSelectedStrategy}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {strategies.map(s => (
                    <SelectItem key={s.id} value={s.id}>
                      <div>
                        <div className="font-medium">{s.name}</div>
                        <div className="text-xs text-gray-500">{s.desc}</div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedType} onValueChange={setSelectedType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="CALL">CALL</SelectItem>
                  <SelectItem value="PUT">PUT</SelectItem>
                </SelectContent>
              </Select>

              <Button className="w-full">Select Strike</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Selected</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 bg-blue-50 rounded-lg text-center">
                <div className="text-3xl font-bold">
                  ${selectedType === 'CALL' ? chain.calls[2].strike : chain.puts[2].strike}
                </div>
                <div className="text-gray-600">{selectedType}</div>
              </div>
              
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-gray-500">Entry</div>
                  <div className="font-medium">
                    ${selectedType === 'CALL' ? chain.calls[2].ask : chain.puts[2].ask}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Delta</div>
                  <div className="font-medium">
                    {selectedType === 'CALL' ? chain.calls[2].delta : chain.puts[2].delta}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">IV</div>
                  <div className="font-medium">
                    {selectedType === 'CALL' ? chain.calls[2].iv : chain.puts[2].iv}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">OI</div>
                  <div className="font-medium">
                    {selectedType === 'CALL' ? chain.calls[2].oi : chain.puts[2].oi}
                  </div>
                </div>
              </div>

              <Button variant="outline" className="w-full">
                Execute Trade
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Compare Tab */}
      {activeTab === 'compare' && (
        <Card>
          <CardHeader>
            <CardTitle>Compare Strategies</CardTitle>
            <CardDescription>Compare different strike selections</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full">
              <thead>
                <tr className="text-gray-500 text-sm border-b">
                  <th className="text-left p-2">Strategy</th>
                  <th className="text-right p-2">Strike</th>
                  <th className="text-right p-2">Price</th>
                  <th className="text-right p-2">Delta</th>
                  <th className="text-right p-2">IV</th>
                  <th className="text-right p-2">ROI</th>
                </tr>
              </thead>
              <tbody>
                {strategies.slice(0, 5).map((s, i) => (
                  <tr key={s.id} className="border-b hover:bg-gray-50">
                    <td className="p-2 font-medium">{s.name}</td>
                    <td className="p-2 text-right">
                      ${selectedType === 'CALL' ? chain.calls[i].strike : chain.puts[i].strike}
                    </td>
                    <td className="p-2 text-right">
                      ${selectedType === 'CALL' ? chain.calls[i].bid : chain.puts[i].bid}
                    </td>
                    <td className="p-2 text-right">
                      {selectedType === 'CALL' ? chain.calls[i].delta : chain.puts[i].delta}
                    </td>
                    <td className="p-2 text-right">
                      {selectedType === 'CALL' ? chain.calls[i].iv : chain.puts[i].iv}%
                    </td>
                    <td className="p-2 text-right text-green-600">
                      +{(Math.random() * 50).toFixed(0)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default StrikeSelectionPage;
