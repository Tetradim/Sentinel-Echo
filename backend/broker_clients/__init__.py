import aiohttp
import logging
import re
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from models import BrokerConfig, BrokerType

logger = logging.getLogger(__name__)

# Default timeout for API requests
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)


def _secret_value(value) -> str:
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return value or ""


def _int_quantity(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_price(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class OrderValidationError(Exception):
    """Raised when order parameters fail validation"""
    pass


class BaseBrokerClient(ABC):
    # Valid values
    VALID_SIDES = {'BUY', 'SELL'}
    VALID_OPTION_TYPES = {'CALL', 'PUT'}
    TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}$')
    EXPIRATION_PATTERNS = [
        re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$'),  # MM/DD/YY or MM/DD/YYYY
        re.compile(r'^\d{4}-\d{2}-\d{2}$'),         # YYYY-MM-DD
        re.compile(r'^\d{6,8}$'),                    # YYMMDD or YYYYMMDD
    ]
    
    # Limits
    MAX_QUANTITY = 10000
    MAX_PRICE = 100000.0
    MAX_STRIKE = 100000.0
    
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.connected = False
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a reusable aiohttp session with connection pooling"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,  # Max connections per host
                limit_per_host=5,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=DEFAULT_TIMEOUT,
                raise_for_status=False
            )
        return self._session
    
    async def close(self):
        """Close the aiohttp session - call when done with the client"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures session cleanup"""
        await self.close()
    
    def validate_order(self, ticker: str, strike: float, option_type: str,
                       expiration: str, side: str, quantity: int, price: float) -> Tuple[bool, Optional[str]]:
        """
        Validate all order parameters before placing an order.
        Returns (is_valid, error_message)
        """
        errors = []
        
        # Ticker validation
        if not ticker:
            errors.append("Ticker is required")
        elif not isinstance(ticker, str):
            errors.append(f"Ticker must be a string, got {type(ticker).__name__}")
        elif not self.TICKER_PATTERN.match(ticker.upper()):
            errors.append(f"Invalid ticker format: '{ticker}'. Must be 1-5 uppercase letters")
        
        # Strike validation
        if strike is None:
            errors.append("Strike price is required")
        elif not isinstance(strike, (int, float)):
            errors.append(f"Strike must be a number, got {type(strike).__name__}")
        elif strike <= 0:
            errors.append(f"Strike must be positive, got {strike}")
        elif strike > self.MAX_STRIKE:
            errors.append(f"Strike exceeds maximum ({self.MAX_STRIKE}), got {strike}")
        
        # Option type validation
        if not option_type:
            errors.append("Option type is required")
        elif not isinstance(option_type, str):
            errors.append(f"Option type must be a string, got {type(option_type).__name__}")
        elif option_type.upper() not in self.VALID_OPTION_TYPES:
            errors.append(f"Invalid option type: '{option_type}'. Must be CALL or PUT")
        
        # Expiration validation
        if not expiration:
            errors.append("Expiration date is required")
        elif not isinstance(expiration, str):
            errors.append(f"Expiration must be a string, got {type(expiration).__name__}")
        else:
            valid_exp = any(pattern.match(expiration) for pattern in self.EXPIRATION_PATTERNS)
            if not valid_exp:
                errors.append(f"Invalid expiration format: '{expiration}'. Use MM/DD/YY, YYYY-MM-DD, or YYMMDD")
        
        # Side validation
        if not side:
            errors.append("Side is required")
        elif not isinstance(side, str):
            errors.append(f"Side must be a string, got {type(side).__name__}")
        elif side.upper() not in self.VALID_SIDES:
            errors.append(f"Invalid side: '{side}'. Must be BUY or SELL")
        
        # Quantity validation
        if quantity is None:
            errors.append("Quantity is required")
        elif not isinstance(quantity, int):
            errors.append(f"Quantity must be an integer, got {type(quantity).__name__}")
        elif quantity <= 0:
            errors.append(f"Quantity must be positive, got {quantity}")
        elif quantity > self.MAX_QUANTITY:
            errors.append(f"Quantity exceeds maximum ({self.MAX_QUANTITY}), got {quantity}")
        
        # Price validation
        if price is None:
            errors.append("Price is required")
        elif not isinstance(price, (int, float)):
            errors.append(f"Price must be a number, got {type(price).__name__}")
        elif price <= 0:
            errors.append(f"Price must be positive, got {price}")
        elif price > self.MAX_PRICE:
            errors.append(f"Price exceeds maximum ({self.MAX_PRICE}), got {price}")
        
        if errors:
            return False, "; ".join(errors)
        return True, None
    
    def _validate_and_normalize(self, ticker: str, strike: float, option_type: str,
                                 expiration: str, side: str, quantity: int, price: float) -> dict:
        """
        Validate and normalize order parameters.
        Raises OrderValidationError if validation fails.
        Returns normalized parameters dict.
        """
        is_valid, error = self.validate_order(ticker, strike, option_type, expiration, side, quantity, price)
        if not is_valid:
            logger.error(f"Order validation failed: {error}")
            raise OrderValidationError(error)
        
        return {
            'ticker': ticker.upper().strip(),
            'strike': float(strike),
            'option_type': option_type.upper().strip(),
            'expiration': expiration.strip(),
            'side': side.upper().strip(),
            'quantity': int(quantity),
            'price': round(float(price), 2)
        }
    
    @abstractmethod
    async def check_connection(self) -> bool:
        pass
    
    @abstractmethod
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        pass


class IBKRClient(BaseBrokerClient):
    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.config.gateway_url}/v1/api/iserver/auth/status",
                ssl=False, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.connected = data.get('authenticated', False)
                    return self.connected
        except Exception as e:
            logger.error(f"IBKR connection error: {e}")
        return False

    async def _lookup_conid(self, ticker: str, option_type: str,
                            expiration_yymmdd: str, strike: float) -> str:
        """
        C11: Look up a real numeric conid from IBKR's /iserver/secdef/search endpoint.
        Returns the conid string if found, raises RuntimeError otherwise.
        """
        session = await self._get_session()
        # Step 1: search for the underlying symbol
        async with session.post(
            f"{self.config.gateway_url}/v1/api/iserver/secdef/search",
            json={"symbol": ticker, "secType": "OPT", "name": True},
            ssl=False,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"IBKR secdef search failed: HTTP {resp.status}")
            results = await resp.json()

        if not results:
            raise RuntimeError(f"IBKR: no contracts found for {ticker}")

        # Step 2: get option strikes/expirations for the first matching contract
        conid_base = results[0].get('conid')
        if not conid_base:
            raise RuntimeError(f"IBKR: no base conid in secdef result for {ticker}")

        opt_right = 'C' if option_type.upper() == 'CALL' else 'P'
        # IBKR expiration format: YYYYMMDD -- our internal format is YYMMDD
        expiry_full = f"20{expiration_yymmdd}" if len(expiration_yymmdd) == 6 else expiration_yymmdd

        async with session.get(
            f"{self.config.gateway_url}/v1/api/iserver/secdef/strikes",
            params={
                "conid": conid_base,
                "sectype": "OPT",
                "month": expiry_full[:6],  # YYYYMM
                "right": opt_right,
            },
            ssl=False,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"IBKR strikes lookup failed: HTTP {resp.status}")
            strikes_data = await resp.json()

        # Step 3: find the conid for the specific strike
        call_or_put_key = 'call' if opt_right == 'C' else 'put'
        strikes_list = strikes_data.get(call_or_put_key, [])
        for entry in strikes_list:
            if abs(float(entry.get('strike', -1)) - strike) < 0.001:
                conid = str(entry.get('conid', ''))
                if conid:
                    logger.info("IBKR conid for %s %s %s @%.2f = %s",
                                ticker, opt_right, expiry_full, strike, conid)
                    return conid

        raise RuntimeError(
            f"IBKR: no conid found for {ticker} {opt_right} {expiry_full} strike={strike}"
        )

    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        try:
            try:
                params = self._validate_and_normalize(ticker, strike, option_type, expiration, side, quantity, price)
            except OrderValidationError as e:
                return {'error': f'Validation failed: {str(e)}'}

            if not self.connected:
                await self.check_connection()
            if not self.connected:
                return {'error': 'Not connected to IBKR'}

            exp_parts = params['expiration'].split('/')
            if len(exp_parts) == 3:
                exp_yymmdd = f"{exp_parts[2]}{exp_parts[0].zfill(2)}{exp_parts[1].zfill(2)}"
            else:
                exp_yymmdd = params['expiration'].replace('/', '')

            # C11: look up the real numeric conid
            try:
                conid = await self._lookup_conid(
                    params['ticker'], params['option_type'], exp_yymmdd, params['strike']
                )
            except RuntimeError as e:
                return {'error': f'Contract lookup failed: {e}'}

            order_data = {
                'orders': [{
                    'conid': conid,
                    'orderType': 'LMT',
                    'side': params['side'],
                    'quantity': params['quantity'],
                    'price': params['price'],
                    'tif': 'DAY'
                }]
            }

            session = await self._get_session()
            async with session.post(
                f"{self.config.gateway_url}/v1/api/iserver/account/{self.config.account_id}/orders",
                json=order_data, ssl=False
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'order_id': data[0].get('order_id'), 'status': 'submitted'}
                return {'error': f'Order failed: {resp.status}'}
        except Exception as e:
            logger.error(f"IBKR order failed: {e}")
            return {'error': str(e)}


class AlpacaClient(BaseBrokerClient):
    def _get_headers(self):
        return {
            'APCA-API-KEY-ID': _secret_value(self.config.api_key),
            'APCA-API-SECRET-KEY': _secret_value(self.config.api_secret)
        }
    
    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.config.base_url}/v2/account",
                headers=self._get_headers()
            ) as resp:
                self.connected = resp.status == 200
                return self.connected
        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        try:
            # Validate inputs first
            try:
                params = self._validate_and_normalize(ticker, strike, option_type, expiration, side, quantity, price)
            except OrderValidationError as e:
                return {'error': f'Validation failed: {str(e)}'}
            
            if not self.connected:
                await self.check_connection()
            if not self.connected:
                return {'error': 'Not connected to Alpaca'}
            
            exp_parts = params['expiration'].split('/')
            if len(exp_parts) == 3:
                exp_formatted = f"{exp_parts[2]}-{exp_parts[0].zfill(2)}-{exp_parts[1].zfill(2)}"
            else:
                exp_formatted = params['expiration']
            
            opt_type = 'C' if params['option_type'] == 'CALL' else 'P'
            symbol = f"{params['ticker']}{exp_formatted.replace('-', '')}{opt_type}{int(params['strike'] * 1000):08d}"
            
            order_data = {
                'symbol': symbol,
                'qty': params['quantity'],
                'side': params['side'].lower(),
                'type': 'limit',
                'limit_price': str(params['price']),
                'time_in_force': 'day'
            }
            if client_order_id:
                order_data['client_order_id'] = client_order_id
            
            session = await self._get_session()
            async with session.post(
                f"{self.config.base_url}/v2/orders",
                headers=self._get_headers(), json=order_data
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    return {'order_id': data.get('id'), 'status': 'submitted'}
                data = await resp.json()
                return {'error': data.get('message', 'Order failed')}
        except Exception as e:
            logger.error(f"Alpaca order failed: {e}")
            return {'error': str(e)}

    async def get_order_status(self, order_id: str) -> dict:
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.config.base_url}/v2/orders/{order_id}",
                headers=self._get_headers(),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    return {
                        'status': 'error',
                        'filled_qty': 0,
                        'avg_fill_price': 0.0,
                        'reason': data.get('message', f'Alpaca order lookup failed: {resp.status}'),
                    }

                raw_status = str(data.get('status') or 'unknown').lower()
                status = {
                    'partially_filled': 'partial',
                    'canceled': 'cancelled',
                }.get(raw_status, raw_status)
                return {
                    'status': status,
                    'filled_qty': _int_quantity(data.get('filled_qty')),
                    'avg_fill_price': _float_price(data.get('filled_avg_price')),
                    'reason': data.get('reject_reason') or data.get('cancel_reason') or '',
                }
        except Exception as e:
            logger.error(f"Alpaca order status lookup failed: {e}")
            return {
                'status': 'error',
                'filled_qty': 0,
                'avg_fill_price': 0.0,
                'reason': str(e),
            }


class TDAmeritadeClient(BaseBrokerClient):
    def _get_headers(self):
        return {'Authorization': f'Bearer {_secret_value(self.config.access_token)}'}
    
    async def check_connection(self) -> bool:
        try:
            if not _secret_value(self.config.refresh_token):
                return False
            session = await self._get_session()
            async with session.get(
                'https://api.schwabapi.com/trader/v1/accounts',
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    self.connected = True
                    return True
                elif resp.status == 401:
                    return await self._refresh_token()
        except Exception as e:
            logger.error(f"TD Ameritrade connection error: {e}")
        return False
    
    async def _refresh_token(self) -> bool:
        try:
            import base64
            credentials = base64.b64encode(
                f"{self.config.client_id}:{_secret_value(self.config.api_secret)}".encode()
            ).decode()
            headers = {'Authorization': f'Basic {credentials}', 'Content-Type': 'application/x-www-form-urlencoded'}
            data = {'grant_type': 'refresh_token', 'refresh_token': _secret_value(self.config.refresh_token)}
            
            session = await self._get_session()
            async with session.post(
                'https://api.schwabapi.com/v1/oauth/token',
                headers=headers, data=data
            ) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self.config.access_token = token_data.get('access_token', '')
                    self.connected = True
                    return True
        except Exception as e:
            logger.error(f"TD Ameritrade token refresh failed: {e}")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'TD Ameritrade order not fully implemented'}


class TradierClient(BaseBrokerClient):
    def _get_headers(self):
        return {'Authorization': f'Bearer {_secret_value(self.config.access_token)}', 'Accept': 'application/json'}
    
    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(
                'https://api.tradier.com/v1/user/profile',
                headers=self._get_headers()
            ) as resp:
                self.connected = resp.status == 200
                return self.connected
        except Exception as e:
            logger.error(f"Tradier connection error: {e}")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        try:
            # Validate inputs first
            try:
                params = self._validate_and_normalize(ticker, strike, option_type, expiration, side, quantity, price)
            except OrderValidationError as e:
                return {'error': f'Validation failed: {str(e)}'}
            
            if not self.connected:
                await self.check_connection()
            if not self.connected:
                return {'error': 'Not connected to Tradier'}
            
            exp_parts = params['expiration'].split('/')
            if len(exp_parts) == 3:
                exp_formatted = f"{exp_parts[2]}-{exp_parts[0].zfill(2)}-{exp_parts[1].zfill(2)}"
            else:
                exp_formatted = params['expiration']
            
            opt_type = 'C' if params['option_type'] == 'CALL' else 'P'
            symbol = f"{params['ticker']}{exp_formatted.replace('-', '')}{opt_type}{int(params['strike'] * 1000):08d}"
            
            order_data = {
                'class': 'option',
                'symbol': params['ticker'],
                'option_symbol': symbol,
                'side': 'buy_to_open' if params['side'] == 'BUY' else 'sell_to_close',
                'quantity': params['quantity'],
                'type': 'limit',
                'price': params['price'],
                'duration': 'day'
            }
            
            session = await self._get_session()
            async with session.post(
                f'https://api.tradier.com/v1/accounts/{self.config.account_id}/orders',
                headers=self._get_headers(), data=order_data
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    order_info = data.get('order', {})
                    return {'order_id': order_info.get('id'), 'status': 'submitted'}
                data = await resp.json()
                return {'error': data.get('error', 'Order failed')}
        except Exception as e:
            logger.error(f"Tradier order failed: {e}")
            return {'error': str(e)}


class WebullClient(BaseBrokerClient):
    async def check_connection(self) -> bool:
        logger.warning("Webull requires manual authentication")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'Webull API not implemented'}


class RobinhoodClient(BaseBrokerClient):
    async def check_connection(self) -> bool:
        # FIXED C12: was returning True whenever credentials existed — never verified connectivity
        logger.warning("Robinhood API not implemented — cannot verify connection")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'Robinhood API requires robin_stocks library'}


class TradeStationClient(BaseBrokerClient):
    def _get_headers(self):
        return {'Authorization': f'Bearer {_secret_value(self.config.access_token)}'}
    
    async def check_connection(self) -> bool:
        try:
            if not _secret_value(self.config.ts_refresh_token):
                return False
            session = await self._get_session()
            async with session.get(
                'https://api.tradestation.com/v3/brokerage/accounts',
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    self.connected = True
                    return True
                elif resp.status == 401:
                    return await self._refresh_token()
        except Exception as e:
            logger.error(f"TradeStation connection error: {e}")
        return False
    
    async def _refresh_token(self) -> bool:
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.config.ts_client_id,
                'client_secret': _secret_value(self.config.ts_client_secret),
                'refresh_token': _secret_value(self.config.ts_refresh_token),
                'redirect_uri': self.config.ts_redirect_uri
            }
            
            session = await self._get_session()
            async with session.post(
                'https://signin.tradestation.com/oauth/token',
                data=data
            ) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self.config.access_token = token_data.get('access_token', '')
                    self.connected = True
                    return True
        except Exception as e:
            logger.error(f"TradeStation token refresh failed: {e}")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'TradeStation order not fully implemented'}


class ThinkorswimClient(BaseBrokerClient):
    def _get_headers(self):
        return {'Authorization': f'Bearer {_secret_value(self.config.access_token)}'}
    
    async def check_connection(self) -> bool:
        try:
            if not _secret_value(self.config.tos_refresh_token):
                return False
            session = await self._get_session()
            async with session.get(
                'https://api.schwabapi.com/trader/v1/accounts',
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    self.connected = True
                    return True
                elif resp.status == 401:
                    return await self._refresh_token()
        except Exception as e:
            logger.error(f"Thinkorswim connection error: {e}")
        return False
    
    async def _refresh_token(self) -> bool:
        try:
            import base64
            credentials = base64.b64encode(f"{self.config.tos_consumer_key}:".encode()).decode()
            headers = {'Authorization': f'Basic {credentials}', 'Content-Type': 'application/x-www-form-urlencoded'}
            data = {'grant_type': 'refresh_token', 'refresh_token': _secret_value(self.config.tos_refresh_token)}
            
            session = await self._get_session()
            async with session.post(
                'https://api.schwabapi.com/v1/oauth/token',
                headers=headers, data=data
            ) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self.config.access_token = token_data.get('access_token', '')
                    self.connected = True
                    return True
        except Exception as e:
            logger.error(f"Thinkorswim token refresh failed: {e}")
        return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'Thinkorswim order not fully implemented'}


class WealthsimpleClient(BaseBrokerClient):
    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self.access_token = None
    
    async def check_connection(self) -> bool:
        try:
            if not self.config.ws_email or not _secret_value(self.config.ws_password):
                return False
            
            auth_url = "https://trade-service.wealthsimple.com/auth/login"
            headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
            auth_data = {'email': self.config.ws_email, 'password': _secret_value(self.config.ws_password)}
            
            if self.config.ws_otp_code:
                auth_data['otp'] = self.config.ws_otp_code
            
            session = await self._get_session()
            async with session.post(
                auth_url, headers=headers, json=auth_data
            ) as resp:
                if resp.status == 200:
                    self.access_token = resp.headers.get('X-Access-Token')
                    if self.access_token:
                        self.connected = True
                        return True
            return False
        except Exception as e:
            logger.error(f"Wealthsimple connection error: {e}")
            return False
    
    async def place_order(
        self,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        side: str,
        quantity: int,
        price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        return {'error': 'Wealthsimple order not fully implemented'}


def get_broker_client(broker_type: BrokerType, config: BrokerConfig) -> BaseBrokerClient:
    clients = {
        BrokerType.IBKR: IBKRClient,
        BrokerType.ALPACA: AlpacaClient,
        BrokerType.TD_AMERITRADE: TDAmeritadeClient,
        BrokerType.TRADIER: TradierClient,
        BrokerType.WEBULL: WebullClient,
        BrokerType.ROBINHOOD: RobinhoodClient,
        BrokerType.TRADESTATION: TradeStationClient,
        BrokerType.THINKORSWIM: ThinkorswimClient,
        BrokerType.WEALTHSIMPLE: WealthsimpleClient,
    }
    return clients[broker_type](config)
