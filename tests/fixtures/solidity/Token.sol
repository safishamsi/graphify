// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address holder) external view returns (uint256);
    event Transfer(address indexed from, address indexed to, uint256 value);
}

library SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }
}

contract Token is IERC20 {
    using SafeMath for uint256;

    mapping(address => uint256) private _balances;

    function balanceOf(address holder) external view returns (uint256) {
        return _balances[holder];
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _balances[msg.sender] = _balances[msg.sender].add(amount);
        emit Transfer(msg.sender, to, amount);
        return true;
    }
}
